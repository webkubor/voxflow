# Agent 自愈遥测（log/）

> 这些日志是**给 AI agent 读的运行时视野**；项目体检在 `log/project-guide.json`，提交前 guard 报告在 `log/guard-report.json`，给人和 agent 共用。
> 由 vite-plugin-agent-eyes 产生，仅本地 dev，**每次启动清空**（只反映本次会话），`*.log` 不入库。
> 若需要完整 agent 操作手册，读包内 `AGENT_GUIDE.md`；若要让 Codex/Claude/Gemini/Hermes 主动发现，读 `AGENT_BOOTSTRAP.md`；README 面向人类安装和 API 评估。

## 排查顺序（读日志 → 定位 → 改 → 重启 dev → 再读验证）

1. **../project-guide.json** —— 先看项目类型、API/业务/路由/配置层级和 `@` alias 建议，决定从哪下钻。
2. **errors.log** —— 再看"哪坏了"：顶部是 Top Errors（聚合去重 + 频率），下方是最近原始记录。
3. **console.log** —— 全级别控制台输出（log/warn/error/info/debug），React dev warning、库 deprecation 警告都在这里。
4. **interaction.log** —— click/input/change/submit/route 脱敏交互轨迹，用来还原复现路径（表单值只记 <redacted>）。
5. **api-calls.log** —— 若是接口问题：看真实请求/响应体（别凭类型猜字段）、调用顺序。
6. **proxy-<host>.log** —— 若是网络/鉴权层：请求带的 Cookie、响应的 Set-Cookie 属性、status。多个代理各自按 target host 分文件。fetch 看不到这层。
7. **auth-state.json** —— 若要还原已登录 UI：看最近一次登录成功的脱敏账号画像。
8. **snapshots/** —— 错误时自动截图（PNG）+ DOM 快照（HTML），视觉+结构双重现场。

最新记录在文件**最上方**（header 之后），`head` 即看本次会话最近发生了什么。
errors.log 的 Top Errors 区直接告诉你"哪个错误刷得最凶"，省去自己数频率。

## 典型：登录成功却一直 401（cookie 存不住）
api-calls.log 见 `POST .../login code=0` 紧跟 `GET .../session 401`
→ proxy-<host>.log 看那条 session 的 Cookie(req)：若为「无」，说明浏览器没存住登录 cookie。
常见根因：上游 Set-Cookie 带父域 Domain + Secure + SameSite=None，http://localhost 域不匹配且 Secure 被丢弃。
修复：agentProxy 已在 dev 对 Set-Cookie 去 Domain / 剥 Secure / SameSite=None→Lax。

## 错误截图 + DOM 快照（snapshots/）
开启 `agentDebugger({ screenshots: true })` 后，每次前端错误或 API 失败自动截取当前页面 PNG，存入 log/snapshots/err-{timestamp}.png。
DOM 快照（log/snapshots/dom-{timestamp}.html）始终启用——错误时自动 dump document.body 结构，agent 可解析。
需要 Chrome 带 `--remote-debugging-port` 启动（仅截图需要，DOM 快照不需要）。插件自动检测端口，未找到时静默跳过。
