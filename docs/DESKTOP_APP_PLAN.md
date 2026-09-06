# VoxFlow 桌面版落地计划

把现在这套 Python + Vue 的本地服务，打成 macOS 和 Windows 都能双击运行的应用。

这份文档给**接手的人（含 agent）**看。凡是标「实测」的都是 2026-09-06 在这台机器上
量出来的数字，标「待验」的就是真的还没验过 —— **不要把待验的当成已知**，
那正是这个项目今天栽过最多次的地方。

---

## 结论先说

**拆成两个构建，先做发布版。**

| 构建 | 体积 | 给谁 | 含什么 |
|---|---|---|---|
| **发布版** | ~60 MB | 只发歌的人 | 发行流水线、台账、通知、R2、自动填表 |
| 完整版 | ~2.2 GB | 做歌的人 | 上面全部 + 本地 TTS（模型另下 7 GB） |

**外壳选 Tauri，Python 作为 sidecar。**

先做发布版的理由不是它简单，是它**对应一类真实存在的用户** ——
项目里已经识别出两类人，需求完全不重叠：做歌的要 7 GB 模型 + Suno 会员，
发歌的只需要拿到音频去上架。后者今天已经能用（「自动化发布」那一屏），
只是还得先装 Python。

---

## 一、为什么能拆（实测）

整条发行链路的模块 —— `core/pipeline.py`、`core/notify.py`、`core/r2.py`、
`core/net.py`、`core/cover.py`、`core/db.py`、`core/obs.py` ——
**对 torch / transformers / librosa / soundfile 的引用数是 0**。

而 `web/app.py` 里的 `import torch` 写在**函数内部**（第 329、365 行），
不是顶层导入。意味着**不装 torch 也能把服务起起来**，
只有真去点「声音克隆」那一屏才会失败 —— 而发布版里那一屏本来就不显示
（`MainLayout.vue` 的 `visibleGroups` 已经做了：没下模型就整个一级入口不显示）。

### 依赖体积（实测，`.venv` 共 1.4 GB）

| 包 | 体积 | 发布版要吗 |
|---|---|---|
| soundfile | **1289 MB** | ✗ |
| torch | 501 MB | ✗ |
| transformers | 107 MB | ✗ |
| onnxruntime | 79 MB | ✗ |
| PIL | 14 MB | ✓（封面尺寸校验） |
| fastapi | 1 MB | ✓ |

> ⚠️ `soundfile` 那 1.3 GB 很反常 —— 它本体只是 libsndfile 的绑定，不该这么大，
> 很可能 wheel 里带了整套预编译二进制。发布版不需要它，但**完整版会被它拖累**。
> 接手的人先量一次再决定要不要换 `audioread` 或直接调 ffmpeg。

---

## 二、技术选型：Tauri

| 方案 | 体积 | Windows 风险 | 判断 |
|---|---|---|---|
| **Tauri + Python sidecar** | ~60 MB | 低 | **选它** |
| Electron + Python sidecar | ~180 MB | 低 | 白背 150 MB Chromium |
| PyInstaller / Nuitka | ~90 MB | 中 | 没有原生窗口；torch 打包在 Windows 上易缺 DLL |
| 纯 Web + 云端跑 | — | 高 | 不做，见「不做的事」 |

Tauri 胜出的真正原因**不是体积，是它不和浏览器抢角色**。

自动化发布依赖 `browser-harness` 附着到**用户日常那个 Chrome**（才有平台登录态）。
Electron 再塞一个 Chromium 进来，只会让人搞不清「到底登在哪个浏览器里」——
这个混淆今天真实发生过一次（browser-harness 看日常 Chrome、ego-browser 是独立上下文，
两边登的是不同账号）。

---

## 三、四个阶段

### 阶段 1：拆平台耦合（1–2 天，不碰打包）

这一步不产出安装包，但它是后面所有事的前提。已定位的硬编码：

| 位置 | 问题 | 改法 |
|---|---|---|
| `web/app.py:2546` | `SUNO_BIN = ~/.cargo/bin/suno` 写死 Unix 路径 | `shutil.which` + 各平台候选路径表 |
| `web/app.py:2568` | `lsof` 只有 Unix 有（用来清残留的验证码 Chrome） | Windows 走 `netstat -ano`，或统一改 `psutil` |
| `core/version.py:93` | 提示语写着 `./install.sh` | 按平台给不同命令 |
| `core/processor.py`<br>`core/modes/dialogue.py` | `pydub` 依赖 `audioop`（Python 3.13 起被移除） | 音频处理收敛到一处，直接调 ffmpeg |
| `run.sh` | 用 `cs kyvault` 注密钥 —— **那是作者的私人工具，别人没有** | 换系统钥匙串（`keyring` 库：Mac Keychain / Windows Credential Manager） |
| `core/paths.py:39` | `~/.voxflow` 在 Windows 上不是标准位置 | Windows 用 `%LOCALAPPDATA%\VoxFlow`，保留 `VOXFLOW_HOME` 覆盖 |

**验收**：在一台干净的 Windows 上 `pip install -e .`（不含 tts 组）后，
`voice web` 能起来，「自动化发布 / 发歌记录 / 运营台」三屏都能用。

### 阶段 2：依赖分组（1 天）

- `[project.dependencies]` 只留发行链路要的：fastapi、uvicorn、python-multipart、pillow、certifi
- `[project.optional-dependencies].tts` 放 torch、transformers、torchaudio、soundfile、librosa、onnxruntime
- 补 `GET /api/capabilities`，让前端知道当前是哪个构建 —— **不要靠猜**

**验收**：`pip install voxflow` 装完 < 100 MB；`pip install voxflow[tts]` 才拉 torch。

### 阶段 3：Tauri 壳 + 发布版安装包（3–5 天）

- Tauri 起壳，窗口内嵌 localhost，启动拉起 Python sidecar、退出收掉
- Python 侧用 [python-build-standalone](https://github.com/indygreg/python-build-standalone)
  打成可移植运行时，随包分发（不依赖用户机器上的 Python）
- **ffmpeg 按平台打进包** —— 今天转 mp3 就靠它（29 MB wav 传不上汽水，必须转 320k mp3）
- 签名与公证：macOS 要 Developer ID + notarize，Windows 要代码签名证书。
  **未签名包在两个系统上都会被拦，装不上比丑更致命**
- 自动更新：Tauri updater 接 GitHub Releases，替掉 `core/version.py` 里「跑 git pull」那套

**验收**：`VoxFlow-0.6.0-arm64.dmg` 与 `VoxFlow-0.6.0-x64.msi`；
在没装过 Python 的机器上双击能用，贴一个 R2 链接能走完备料。

### 阶段 4：完整版（5–8 天，风险集中）

- torch 选 CPU wheel（`--index-url download.pytorch.org/whl/cpu`），**别把 CUDA 打进去**
- 模型不进安装包，首次进「音色」那屏再下（`ModelSetupCard` 已经有了）
- Mac 走 MPS、Windows 走 CPU（或可选 DirectML）—— **这里要实测，不能假设**
- 把 `soundfile` 那 1.3 GB 查清楚再决定留不留

**验收**：Windows CPU 上克隆一段 10 秒音频，耗时可接受
（先量出基线再定「可接受」是多少，别拍脑袋）。

---

## 四、外部 CLI 依赖

现在有四个外部命令行工具被代码直接调用。它们不是 Python 包，装不进 wheel。

| 工具 | 用途 | 形态 | Windows | 处置 |
|---|---|---|---|---|
| `browser-harness` | 自动填表（附着 Chrome） | Python + CDP | **待验** | 见下方「最该先验的一件事」 |
| `ffmpeg` | 转 mp3、切片段 | 原生二进制 | 好 | 按平台打进包 |
| `suno` | 生成音乐 | Rust 二进制 | 待验 | 只有完整版需要 |
| `museav` | 出封面 | 自有 CLI | 待验 | **✅ 已拍板：改直连 HTTP** |
| `lark-cli` | 飞书台账与群通知 | Node（pnpm） | 要 Node | **✅ 已拍板：改直连 HTTP** |

### 已拍板：`lark-cli` 与 `museav` 改直连 HTTP

两个都已经有 HTTP 接口，改完发布版**不再要求用户装 Node 和额外 CLI**，
外部依赖只剩 ffmpeg（随包）和 Chrome（用户本来就有）。

具体要改的：

- **`core/notify.py` 的 `_lark_cli()` / `_lark_json()`** —— 现在 shell out 到 `lark-cli`。
  改成直接调飞书开放平台：`POST /open-apis/im/v1/messages`（发卡片）、
  `/open-apis/bitable/v1/apps/{app}/tables/{table}/records`（台账读写）。
  需要自己维护 tenant_access_token 的获取与刷新
  （`POST /open-apis/auth/v3/tenant_access_token/internal`，用 app_id + app_secret）。
  webhook 通道保持不变，它本来就是纯 HTTP。

- **`core/cover.py` 的 `generate()`** —— 现在跑 `museav gen`。
  文件头注释里写着「调 HTTP 而不是 CLI」，但 `generate()` 实际走的是 CLI，
  **注释和代码不一致**，接手时以代码为准。同文件的 `_request()` 已经是 HTTP 通道
  （`/templates`、`/balance` 都在用），照它改即可。

> 改完记得删掉 `_museav_bin()` / `_museav_logged_in()` 和 `available()` 里对 CLI 的检查，
> 换成「有没有配 base_url + api_key」。`/api/publish/preflight` 那一项也要跟着改。

---

## 五、风险

| 风险 | 级别 | 应对 |
|---|---|---|
| **Windows 上 browser-harness 连不上 Chrome** | 高 | 阶段 1 就先验，别等阶段 3 |
| 代码签名证书（Mac $99/年，Win OV ~$200+/年） | 中 | 钱和时间提前排 |
| torch 在 Windows 缺 DLL（MSVC 运行时） | 中 | 只影响完整版；用 CPU wheel + 干净机器验 |
| 系统 HTTPS 代理让浏览器上传失败 | 中 | **今天栽过**：Reqable 开着时汽水音频上传一直失败。浏览器代理归系统管，代码改不了，只能检测到就提前警告 |
| 短信验证码 / 实名认证 | 已知边界 | 不解决。签协议最后一步只能人来 |

### 最该先验的一件事

**browser-harness 在 Windows 上能不能附着 Chrome。**

这是整个自动化发布的地基。如果不行，桌面版的定位就得变 ——
从「自动发布」退回「备料 + 人工填表」，**那是完全不同的产品承诺**，越早知道越好。

好消息是兜底方案已经做好了：`GET /api/publish/sheet` 把平台表单每一栏的值都算好，
人复制粘贴十分钟填完，**和自动填表同一份数据来源**，不会两边不一致。

---

## 六、不做的事

- **不做云端跑模型。** 本地 TTS 的全部卖点就是不上传，搬上云就没意义了。
- **不打包 Chromium。** 自动化必须用用户自己那个有登录态的浏览器，
  多一个只会让人搞错登在哪。
- **不把 7 GB 模型塞进安装包。** 首次运行按需下载已经做好了，
  塞进去会让所有人 —— 包括只发歌的人 —— 多等两小时。
- **不做全流程无人值守。** 提交进审核不可逆、签协议要短信，最后一下必须留给人。

---

## 七、接手顺序

按依赖顺序，前三件都不需要碰打包：

1. **验 browser-harness 在 Windows 上能不能用**（见「最该先验的一件事」）
2. **把 `lark-cli` 和 `museav` 改成直连 HTTP**（已拍板，见第四节）
3. **拆依赖分组**（改 pyproject 就行，改完立刻能验「不装 torch 服务起不起得来」）

这三件做完，**即使打包还没开始，队友已经可以 `pip install voxflow` 装一个
百兆以内的发布版**。桌面壳是体验升级，不是能用的前提 ——
别让打包挡住可用性。

---

## 附：接手前必读

- **平台 SOP 在 `configs/platforms.json`**，里面记了 21 个实测卡点
  （2026-09-06 走完两首真实发行时补的）。改自动填表脚本前先读那一份，
  尤其是「错误检测」那四条 —— 平台的校验提示是**普通颜色文字**挂在字段下面，
  不是红字，只找红色文字会反复卡在同一个按钮上。
- **不要相信「操作成功」，要读回验证。** 今天最大的时间浪费来自
  「点了就假设成功」：填完表就报「可以发了」，而异步校验还没落定。
  正确的循环是：操作 → 读回 / 截图 → 验证 → 才下一步。
- **约束写在数据库上，别写在代码的 if 里。** 重复的平台记录清了两次才想到
  加 `UNIQUE(track_id, platform, IFNULL(song_id,''))` ——
  「插之前先查一下」防不住，查漏一处就漏一次，而漏掉的那次不报错。
