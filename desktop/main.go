// VoxFlow 声流 —— macOS 原生桌面壳（MyGo）。
//
// ## 这个壳解决什么
//
// 之前用 scripts/make-app.sh 做了一个 Chrome `--app` 模式的壳：双击开窗、
// 没有地址栏。它能用，但终究是浏览器 —— 窗口没有原生菜单、没有系统通知、
// 没有原生文件选择器，而且每台机器都得装 Chrome。
//
// 现在换成 MyGo（WKWebView + Go 层）：窗口、菜单、通知、文件对话框都是系统
// 原生的，前端还是同一份 Vue 代码，一个字没改。
//
// ## 架构
//
//	┌─────────────────────────────────────────────┐
//	│ MyGo 窗口 (WKWebView)                       │
//	│   加载 mygo://localhost/  ← 嵌入式前端产物  │
//	│   fetch('/api/...')  ─────────────┐         │
//	└──────────────────────────────────┼─────────┘
//	                                   │ 代理
//	                        ┌──────────▼─────────┐
//	                        │ Python 后端 :8866  │
//	                        │  (voice web)       │
//	                        └────────────────────┘
//
// 后端没起来时，壳自己拉起来它（复用项目里的 run.sh，不重复实现启动逻辑）。
// 前端产物嵌进 App，离线也能开；后端不通时界面显示失败，而不是空白。
//
// ## 为什么不把后端也编译进 App
//
// 后端依赖 MLX 模型（~/.voxflow/models-mlx，5.8 GB）和 Python venv，
// 打包进去既做不到也背不动。App 只是壳，音频能力仍在项目目录里。

package main

import (
	"embed"
	"fmt"
	"io"
	"io/fs"
	"log"
	"mime"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"

	"github.com/egoist/mygo"
)

//go:embed all:web
var webFiles embed.FS

//go:embed resources/icon.png
var appIcon []byte

const (
	appName = "VoxFlow 声流"
	// backendPort 是本地 Python 后端监听的端口，和 web/app.py 的默认一致。
	backendPort = 8866
	// backendStartTimeout 是等后端就绪的上限。MLX 模型加载慢，
	// 所以给得比一般服务宽裕；超时后仍然打开窗口，让界面自己报告失败。
	backendStartTimeout = 180 * time.Second
	// appVersion 是 App 版本号，和 mygo.json 保持一致。
	appVersion = "0.11.0"
)

// backendURL 返回本地后端地址。只允许回环地址 —— 这个端口上有用户的
// 音色、音频和用量数据，不该被同网段的别的机器读到。
func backendURL() *url.URL {
	raw := os.Getenv("VOXFLOW_API")
	if raw == "" {
		raw = fmt.Sprintf("http://127.0.0.1:%d", backendPort)
	}
	u, err := url.Parse(raw)
	// localhost 和 127.0.0.1 都是回环，只认 127.0.0.1 会让最常见的写法
	// 直接把 App 打死（log.Fatalf），用户看不出是自己写错了什么。
	if err != nil || u.Scheme != "http" || !isLoopback(u.Hostname()) || u.User != nil ||
		(u.Path != "" && u.Path != "/") || u.RawQuery != "" || u.Fragment != "" {
		log.Fatalf("VOXFLOW_API must be a loopback http URL (127.0.0.1 or localhost)")
	}
	return u
}

// isLoopback 判断主机名是否指向本机回环。
func isLoopback(host string) bool {
	if host == "127.0.0.1" || host == "localhost" {
		return true
	}
	// ::1 是 IPv6 的回环写法。
	return host == "::1"
}

// buildProjectDir 是编译期烧进去的项目路径。
//
// App 可能被从任何目录启动，甚至从访达里双击打开 —— 那时没有终端、没有
// 环境变量、没有工作目录。烧进路径是唯一可靠的办法：上一版 Chrome 壳靠
// 脚本自己算相对路径，这一版没有脚本了。
var buildProjectDir = ""

// projectDir 找出项目根目录（含 run.sh 的那一层）。
func projectDir() string {
	if dir := os.Getenv("VOXFLOW_PROJECT"); dir != "" {
		return dir
	}
	if dir := buildProjectDir; dir != "" {
		if _, err := os.Stat(filepath.Join(dir, "run.sh")); err == nil {
			return dir
		}
	}
	// 从可执行文件位置反推：…/VoxFlow.app/Contents/MacOS/VoxFlow
	if exe, err := os.Executable(); err == nil {
		for dir := filepath.Dir(exe); dir != "/" && dir != "."; dir = filepath.Dir(dir) {
			if _, err := os.Stat(filepath.Join(dir, "run.sh")); err == nil {
				return dir
			}
		}
	}
	// 最后退回当前工作目录：开发时在项目根跑 mygo dev 就是对的。
	wd, _ := os.Getwd()
	return wd
}

// ── 后端进程 ──────────────────────────────────────────────

// backendProcess 记录我们拉起来的 Python 后端，退出时收掉。
//
// 只收我们自己起的那个：如果用户本来就在终端里跑了 `voice web`，
// 壳启动时检测到端口已被占用，就直接复用，不去杀别人的进程。
var backendProcess *exec.Cmd

// backendAlive 报告后端是否在响应。
func backendAlive(client *http.Client) bool {
	resp, err := client.Get(backendURL().String() + "/api/health")
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

// startBackend 在后端没跑的时候把它拉起来。
//
// 复用项目自带的 run.sh —— 那里面已经处理了「venv 在哪」「前端产物过期
// 怎么办」这些事，在这里重写一遍只会造出第二套逻辑。
func startBackend(client *http.Client, logFile *os.File) {
	if backendAlive(client) {
		return
	}
	dir := projectDir()
	runSh := filepath.Join(dir, "run.sh")
	if _, err := os.Stat(runSh); err != nil {
		log.Printf("backend not running and %s not found; the UI will report it", runSh)
		return
	}
	cmd := exec.Command(runSh)
	cmd.Dir = dir
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	// 让后端自成进程组：run.sh 会 exec 成 Python，但 Python 还会再 fork
	// 出 MLX 的 worker 进程。只杀组里的主 PID，那些 worker 会留下来继续
	// 占着显存和 8866 端口 —— 下次开 App 就会连上一个没人管的僵尸后端。
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		log.Printf("start backend: %v", err)
		return
	}
	backendProcess = cmd
	log.Printf("backend started (pid %d), waiting for it to answer in background", cmd.Process.Pid)

	// 不要挡住原生窗口启动：首次 MLX 模型加载可能要几十秒，用户应先看到
	// App 界面，而不是盯着一个什么都没有的桌面等后端就绪。
	go func() {
		deadline := time.Now().Add(backendStartTimeout)
		for time.Now().Before(deadline) {
			if backendAlive(client) {
				log.Printf("backend ready")
				return
			}
			time.Sleep(500 * time.Millisecond)
		}
		log.Printf("backend did not become ready within %s", backendStartTimeout)
	}()
}

// stopBackend 收掉我们拉起来的后端。
//
// 只在确实是自己起的那个时才杀。用户自己开的 `voice web` 不归我们管。
func stopBackend() {
	if backendProcess == nil || backendProcess.Process == nil {
		return
	}
	pid := backendProcess.Process.Pid
	log.Printf("stopping backend (pid %d)", pid)
	// 先礼后兵：给整个进程组一个 SIGTERM，让 Python 有机会跑完清理
	// （SQLite 收尾、临时文件删干净）；等一会儿还没死再 SIGKILL。
	//
	// 杀整个组而不是只杀主进程：run.sh exec 出的 Python 自己还会 fork
	// MLX worker，只杀主 PID 会留下一群占着显存的孤儿。
	if pgid, err := syscall.Getpgid(pid); err == nil {
		_ = syscall.Kill(-pgid, syscall.SIGTERM)
	} else {
		_ = backendProcess.Process.Signal(syscall.SIGTERM)
	}
	done := make(chan struct{})
	go func() {
		_, _ = backendProcess.Process.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		log.Printf("backend did not exit in 5s, killing it")
		if pgid, err := syscall.Getpgid(pid); err == nil {
			_ = syscall.Kill(-pgid, syscall.SIGKILL)
		}
		_ = backendProcess.Process.Kill()
	}
}

// ── 前端与代理 ────────────────────────────────────────────

// csp 把窗口锁在自己的源上：脚本、样式、图片、连接都只允许本地。
// 应用要访问的外部站点，一律交给系统浏览器打开。
const csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
	"img-src 'self' data: blob: https:; media-src 'self' data: blob:; " +
	"connect-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'"

// frontend 把嵌入式前端和后端 API 接到一起。
//
// 前端产物（web/static）嵌进 App，所以离线也能开界面；/api 走代理到本地
// Python 后端。后端没起来时 API 返回 502 并带明确错误码，界面据此显示
// 「服务未启动」，而不是把失败伪装成空列表。
func frontend() http.Handler {
	web, err := fs.Sub(webFiles, "web")
	if err != nil {
		log.Fatal(err)
	}
	target := backendURL()
	proxy := httputil.NewSingleHostReverseProxy(target)

	proxy.ModifyResponse = func(r *http.Response) error {
		mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
		if strings.HasPrefix(r.Request.URL.Path, "/api/") {
			// 本地 API 除 JSON 还会回传音频、封面与下载文件，均需放行。
			// HTML/重定向仍拒绝，防止后端错误页意外进入特权窗口。
			allowed := mediaType == "application/json" || mediaType == "text/plain" ||
				mediaType == "application/octet-stream" || strings.HasPrefix(mediaType, "audio/") ||
				strings.HasPrefix(mediaType, "image/")
			if err != nil || !allowed || (r.StatusCode >= 300 && r.StatusCode < 400) {
				_ = r.Body.Close()
				r.StatusCode, r.Status = http.StatusBadGateway, "502 Bad Gateway"
				r.Header = make(http.Header)
				r.Header.Set("Content-Type", "application/json; charset=utf-8")
				r.Body = io.NopCloser(strings.NewReader(
					`{"error":{"code":"VOXFLOW_BACKEND_UNAVAILABLE","message":"本地音频服务没有响应。"}}`))
				r.ContentLength = -1
			}
			return nil
		}
		// 非 API 路径只允许真正的静态资源，不接受后端渲染的页面。
		allowed := map[string]bool{
			"text/html": true, "text/javascript": true, "application/javascript": true,
			"text/css": true, "image/png": true, "image/svg+xml": true,
			"font/woff2": true, "application/json": true,
		}
		if err != nil || r.StatusCode != http.StatusOK || !allowed[mediaType] {
			_ = r.Body.Close()
			r.StatusCode, r.Status = http.StatusNotFound, "404 Not Found"
			r.Header = make(http.Header)
			r.Header.Set("Content-Type", "application/json; charset=utf-8")
			r.Body = io.NopCloser(strings.NewReader(`{"error":{"code":"VOXFLOW_ASSET_MISSING"}}`))
			r.ContentLength = -1
			return nil
		}
		r.Header.Set("Content-Security-Policy", csp)
		return nil
	}

	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.WriteHeader(http.StatusBadGateway)
		fmt.Fprint(w, `{"error":{"code":"VOXFLOW_BACKEND_UNAVAILABLE","message":"本地音频服务没有响应。"}}`)
	}

	base := proxy.Director
	proxy.Director = func(r *http.Request) {
		base(r)
		r.Host = target.Host
		r.Header.Del("Referer")
		r.Header.Del("Origin")
		r.Header.Set("Sec-Fetch-Site", "same-origin")
	}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasPrefix(r.URL.Path, "/api/") || strings.HasPrefix(r.URL.Path, "/assets/") {
			proxy.ServeHTTP(w, r)
			return
		}
		w.Header().Set("Content-Security-Policy", csp)
		// 前端产物整体住在 /static/ 下（Vite 的 base 就是 /static/），
		// 但窗口加载的是根路径。所以根路径要指向 /static/index.html，
		// 否则用户看到的是一份目录列表。
		name := strings.TrimPrefix(r.URL.Path, "/")
		if name == "" || name == "index.html" {
			name = "static/index.html"
		}
		// 自己读文件，不用 http.FileServerFS：后者对目录路径会回 301，
		// 而 MyGo 的 scheme 处理器不跟随重定向 —— 页面收到一个空的 301，
		// 于是窗口一片黑，连一行报错都没有。踩过这个坑。
		data, err := fs.ReadFile(web, name)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", contentType(name))
		w.Header().Set("Cache-Control", "no-store")
		_, _ = w.Write(data)
	})
}

// contentType 按扩展名给出内容类型。嵌入的资源类型是固定的几种，
// 不必引入 mime 的扩展名数据库。
func contentType(name string) string {
	switch {
	case strings.HasSuffix(name, ".html"):
		return "text/html; charset=utf-8"
	case strings.HasSuffix(name, ".js"):
		return "text/javascript; charset=utf-8"
	case strings.HasSuffix(name, ".css"):
		return "text/css; charset=utf-8"
	case strings.HasSuffix(name, ".png"):
		return "image/png"
	case strings.HasSuffix(name, ".svg"):
		return "image/svg+xml"
	case strings.HasSuffix(name, ".woff2"):
		return "font/woff2"
	case strings.HasSuffix(name, ".json"):
		return "application/json; charset=utf-8"
	default:
		return "application/octet-stream"
	}
}

// ── 菜单 ──────────────────────────────────────────────────

// route 是前端 hash 路由。原生菜单直接切路由，比让用户点标签页更快。
const (
	routeDesign   = "/#/design"
	routeClone    = "/#/clone"
	routeDialogue = "/#/dialogue"
	routeGallery  = "/#/gallery"
	routeAttest   = "/#/attest"
	routeOps      = "/#/ops"
)

// navigate 把窗口切到某个前端路由。
//
// 前端是 hash 路由，所以改的是 location.hash，不是整个 URL —— 整页刷新会
// 丢掉已加载的音色库和任务状态。
func navigate(win *mygo.Window, route string) {
	if win == nil {
		return
	}
	_, _ = win.Page().Eval(fmt.Sprintf("location.hash = %q; true", route))
}

// buildMenu 造出原生菜单。
//
// 三组：工作区（各功能页）、服务（启停本地后端、打开数据目录）、
// 帮助（关于）。菜单项和前端标签页一一对应，用户不用在窗口里找标签。
func buildMenu(getWin func() *mygo.Window) *mygo.Menu {
	nav := func(route string) func(*mygo.MenuItem, *mygo.Window) {
		return func(_ *mygo.MenuItem, _ *mygo.Window) {
			navigate(getWin(), route)
		}
	}
	// macOS 的第一个顶层菜单固定用应用菜单角色；否则第一个业务菜单会被
	// 系统当成应用菜单接管，标签消失（曾导致「工作区」整个菜单不见）。
	return mygo.NewMenu([]*mygo.MenuItem{
		{Role: mygo.RoleAppMenu},
		{Label: "工作区", Submenu: []*mygo.MenuItem{
			{Label: "音色设计", Accelerator: "CmdOrCtrl+1", Click: nav(routeDesign)},
			{Label: "文本配音", Accelerator: "CmdOrCtrl+2", Click: nav(routeClone)},
			{Label: "剧本演播", Accelerator: "CmdOrCtrl+3", Click: nav(routeDialogue)},
			mygo.Separator(),
			{Label: "作品展厅", Accelerator: "CmdOrCtrl+4", Click: nav(routeGallery)},
			{Label: "原创存证", Accelerator: "CmdOrCtrl+5", Click: nav(routeAttest)},
			{Label: "成本与健康", Accelerator: "CmdOrCtrl+6", Click: nav(routeOps)},
		}},
		{Label: "服务", Submenu: []*mygo.MenuItem{
			{Label: "启动本地服务", Click: func(_ *mygo.MenuItem, _ *mygo.Window) {
				startBackend(&http.Client{Timeout: 3 * time.Second}, backendLog())
			}},
			{Label: "在浏览器中打开", Click: func(_ *mygo.MenuItem, _ *mygo.Window) {
				_ = mygo.Shell.OpenExternal(backendURL().String())
			}},
			mygo.Separator(),
			{Label: "打开数据目录", Click: func(_ *mygo.MenuItem, _ *mygo.Window) {
				_ = mygo.Shell.OpenPath(dataDir())
			}},
			{Label: "打开输出目录", Click: func(_ *mygo.MenuItem, _ *mygo.Window) {
				_ = mygo.Shell.OpenPath(filepath.Join(dataDir(), "out"))
			}},
		}},
		{Label: "帮助", Submenu: []*mygo.MenuItem{
			{Label: "关于 " + appName, Click: func(_ *mygo.MenuItem, _ *mygo.Window) {
				_, _ = mygo.Dialog.Message(mygo.MessageOptions{
					Type:    mygo.MessageInfo,
					Title:   appName,
					Message: appName,
					Detail: fmt.Sprintf(
						"版本 %s\n本地 AI 音频工作台：语音克隆、音色设计、剧本演播、原创存证。\n\n数据目录：%s",
						appVersion, dataDir()),
				})
			}},
		}},
	})
}

// dataDir 返回数据目录，和 core/paths.py 的 DATA_DIR 一致。
func dataDir() string {
	if dir := os.Getenv("VOXFLOW_DATA_HOME"); dir != "" {
		return dir
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return filepath.Join(home, ".voxflow")
}

// backendLog 打开后端日志文件。App 的标准输出在 GUI 里没人看，日志得落到
// 文件里才有排查价值。
func backendLog() *os.File {
	dir := dataDir()
	if dir == "" {
		return os.Stderr
	}
	if err := os.MkdirAll(filepath.Join(dir, "logs"), 0o755); err != nil {
		return os.Stderr
	}
	name := filepath.Join(dir, "logs", "desktop-backend.log")
	f, err := os.OpenFile(name, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return os.Stderr
	}
	return f
}

// ── 入口 ──────────────────────────────────────────────────

func main() {
	log.SetFlags(log.LstdFlags)
	log.SetPrefix("voxflow: ")

	if runtime.GOOS == "darwin" {
		// 图标烧进包里，访达和程序坞才认得。
		_ = appIcon
	}

	client := &http.Client{Timeout: 3 * time.Second}
	logFile := backendLog()
	defer logFile.Close()
	startBackend(client, logFile)
	defer stopBackend()

	// 收到终止信号时先收后端再退出。
	//
	// defer 只在正常返回时执行 —— 被强退（kill -9）、或者 macOS 在注销
	// 时直接杀进程，defer 都不跑，Python 后端就变成孤儿：继续占着 8866
	// 端口和几 GB 显存，下次开 App 还会连上这个没人管的僵尸服务。
	// 所以信号路径要显式收一次。
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	go func() {
		s := <-sig
		log.Printf("received %s, shutting down", s)
		stopBackend()
		os.Exit(0)
	}()

	// 前端协议：窗口里加载 mygo://localhost/ 拿到嵌入式页面。
	if err := mygo.Protocol.Handle("mygo", frontend()); err != nil {
		log.Fatalf("register protocol: %v", err)
	}

	mygo.App.WhenReady(func() {
		win := mygo.NewWindow(mygo.WindowOptions{
			Title:           appName,
			Width:           1280,
			Height:          880,
			MinWidth:        900,
			MinHeight:       620,
			BackgroundColor: "#0f1115",
			StateKey:        "main",
			URL:             routeClone,
		})
		mygo.App.SetMenu(buildMenu(func() *mygo.Window { return win }))

		// 外部链接交给系统浏览器，不在特权窗口里加载远端内容。
		win.Page().OnWillNavigate(func(e *mygo.NavigateEvent) {
			if !strings.HasPrefix(e.URL, "mygo://") {
				e.PreventDefault()
				_ = mygo.Shell.OpenExternal(e.URL)
			}
		})
	})

	// App.Run 阻塞在事件循环里 —— 没有它，main 立刻返回，进程就退出了，
	// 窗口连一秒都显示不出来。
	if err := mygo.App.Run(); err != nil {
		log.Fatal(err)
	}
}
