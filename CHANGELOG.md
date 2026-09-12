# 更新日志 (Changelog)

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/) 规范。

## [未发布]

（暂无累积改动）

---

## [0.7.0] - 2026-09-12

### 🔊 音频能自动下回本地了 —— 之前的结论是错的

`/api/inbox` 的注释里写着「CDN 直链 403，硬绕这层反爬性价比极低」，据此把
分工定成「人在浏览器点一下下载」。实际抓一次浏览器网络请求就看到：网页
播放器拉的是 `cloudfront.net/1/clip/<id>.m4a`，**无签名、无 Referer 校验、
直接 GET 就是 200**。API 那路的 `audio_url` 确实被写死成 `api/forbidden`，
但那只是 API 一路被关，CDN 一路一直开着。

「能播放就说明音频流一定到了浏览器」—— 这个判断当时没人往下追。
现在 `core/suno_api.download()` 走 CDN，生成完自动入库；`/api/inbox`
从必经之路降级为兜底。

### 🖥 Windows 支持

六处 macOS 写死已去掉：数据根走 `%LOCALAPPDATA%\VoxFlow`、播放按平台分支、
启动前检查从 run.sh 搬进 `voice web`（三平台共用）、补 `run.ps1`。
`tests/test_platform.py` 注入环境验证分支。**未在真机验证过**。

顺带揪出一个真 bug：`core/llm_client.py` 的默认模型写死 `auto`，而对的值
export 在 run.sh 里 —— 不走 run.sh 的人（Windows、或直接 `voice web`）
AI 文案一律报错。配置的默认值不该藏在某个平台的启动脚本里。

### 🎨 UI 收敛

- 主题色收敛成单一真源：同一个 `#6366f1` 原本以两种写法散在 6 个文件共 21 处，
  现在改 `--vf-primary` 一行全站生效（含 naive-ui）。并写明它源自 logo
  （实测色相差 5.4°）、换色要连 logo/favicon/banner 一起换。
- `.ghost-btn` 7 份分叉收拢成全局一份（原本 4 种尺寸，同屏两个按钮大小不一）。
- 清掉 3 处装饰性 emoji；`WarnBanner` 那组因缺图标暂留，已就地标注原因。

### 🧹 suno CLI 残留清零

`scripts/sync_suno.py` / `sync_clip_meta.py` 改直连。修 `sync_suno.py` 里
一个既有 bug：`renamed` 从未初始化，脚本跑到最后一行必崩。

### 🎨 前端 UI 整体重做 + 设计系统收敛

之前的 UI 是各 Tab 各自写样式，重复实现散落。这次重构成：

- **设计系统单一真源**：`tokens.css` 收口颜色 / 阴影 / 圆角 / 间距 / 缓动曲线 /
  布局常量（header / player 高度 / sidebar 宽度）。`App.vue` 通过
  `getComputedStyle` 从 token 读，不再写死两套。改一处全站生效。
- **图标库** `components/Icon.vue`：30 个 lucide 风格 SVG 图标替代跨系统
  不一致的 emoji，描边色走 `currentColor` 跟主题。
- **公共组件**：`WarnBanner`（4 类型统一警告条）/ `CurrentPersonaChip` /
  `TaskTypeBadge` / `PersonaSidebar`（可折叠 + 搜索）。
- **顶栏 Header**：去冗余信息（平台标签 / 版本号 / 构建时间），加任务铃铛 +
  错误日志铃铛 + 能力 chip popover 看完整状态。
- **Tab 导航**：图标 + 文字，自定义按钮（不依赖 n-tabs 默认胶囊样式）。
- **侧栏 PersonaSidebar**：可折叠成 64px 窄条 + 5+ 音色自动出搜索框。
- **全局播放器**：加最小化模式（右下角 56×56 浮窗）、键盘可达（方向键 /
  Home / End / 空格）、路由切到浏览型 tab 自动暂停、修复 `tag="a"` 不渲染
  a 标签的 bug。
- **任务面板**：从右下半抽屉挪到右上角 + 加关闭按钮 + 阶段进度条。
- **PipelineBoard**：进度可视化改成 n-steps 风格（圆点 + 文字 label + 勾），
  当前阶段计数条高亮。
- **资产库**：按今天 / 昨天 / 本周 / 更早分组 + 文件名搜索 + 类型筛选。
- **性能**：每个 Tab 用 `defineAsyncComponent` 异步加载，首屏 index bundle
  从 484KB → 363KB（-25%）。

### 🔭 可观测体系

- **`lib/errors.ts: VoxError`** —— 把 HTTP status / method / url / requestId /
  stack / context 一次性打包。`toError()` 规整 ky 的 HTTPError / TimeoutError /
  普通 Error，调用方不再需要 try/catch 时判类型。
- **请求头透传**：`X-Client-Version` / `X-Client-Tab` / `X-Request-ID` 自动加
  到每个请求。后端日志能按 tab 区分调用来源，前后端用同一 ID 串起来。
- **`stores/errorLog.ts`** —— 持久化最近 200 条错误，60s 内同 fingerprint
  去重合并计数。点击 header 警告铃铛打开面板：完整 HTTP 上下文 +
  「复制详情」一键贴 issue。
- **报告入口统一**：tasks store 新增 `reportError(err, ctx)`，替换之前散在 25
  处的 `showToast(e.message, 'error')`。所有堆栈和 URL 都不再丢。
- **Toast 时长按类型分**：info/success 3s · warning 5s · error 8s · fatal 不自动关。
  `reportError` 落日志 + 弹可关闭 toast。

### ⌨️ 全局快捷键（`composables/useShortcuts.ts`）

| 键 | 动作 |
|---|---|
| `⌘K` / `Ctrl+K` / `/` | 聚焦音色搜索 |
| `Space` | 播放 / 暂停 |
| `M` | 静音 |
| `T` | 任务面板 |
| `E` | 错误日志 |
| `1`-`7` | 切 tab |
| `?` | 快捷键帮助 |
| `Esc` | 关弹窗 |

输入元素里全部失效不打断打字。

### 🎵 Suno 三种生成模式 + 翻唱

之前一个表单所有用户都要填歌词 + 选 persona，但用户意图分三种：
歌曲 / BGM / 翻唱。混在一个表单里用户困惑。

- **`MODES` 三模式切换器**：歌曲 / BGM / 翻唱 segmented control。
- **BGM 模式**：隐藏歌词 / persona 字段，自动追加 `instrumental` 标签 +
  `[Instrumental]` 占位歌词。加 6 个场景预设 chips（专注 / 咖啡 / 助眠 /
  运动 / 影视 / 短视频），前 4 个是抖音热门（卡点 / 深夜伤感 / 励志燃 /
  国潮古风）。
- **翻唱模式**：热点风向每行加「翻唱这首」按钮，点击自动预填原曲名 +
  tags + persona 提到主位「用你的声音翻唱」。
- **`stores/coverHistory.ts`**：跟踪每次翻唱，原曲 / 艺人 / persona /
  hasSourceAudio / 状态 / URL。Suno 任务轮询完成时按 task_id reconcile。
- **翻唱历史面板**：「真翻唱 🎵」/「文本借鉴 📝」徽章区分是否上传了原曲音频。
- **`POST /api/suno/cover`**（前端接通，后端待实现）：上传原曲音频做真
  「同曲不同演绎」。Suno covers API 端点，前端 FormData 已就位。

### ⚙️ Suno 额度可视化

- **顶栏能力 chip** 显示 `Pro · 20/2500`（已用 / 总额）。
- **popover** 完整信息：状态 / 套餐 / 剩余 / 已用 / 续费日。
- **SunoTab 头部** 倒计时提示：「明日重置」「N 天后重置」「下月 M/D 重置」。
- 后端 `/api/capabilities` 需返回 `credits_total` 和 `renew_date`，
  前端**优雅降级** —— 字段缺失就不显示对应行，不报错。

### 📦 批量生成（前端 + 后端 + 脚本）

- **SunoTab BGM 模式批量面板** `commit cb561a7`：填多行（标题 + preset）→
  点 1 次「开始批量」自动顺序提交，3 秒间隔避 Suno 速率限制。
- **后端 `POST /api/suno/batch`** `commit 7cce7be`：≤20 首 / 任务，自动
  间隔 2 秒，`wait=true` 同步轮询全部完成才返回。走现有 `_submit_task`
  任务队列，跟单首 `/api/suno/generate` 同一条路径，不旁路。
- **`scripts/batch_bgm.py`**：CLI 调 voxflow 后端 HTTP API，**不碰 suno CLI**。
  用法：
  `./scripts/batch_bgm.py "破晓:epic orchestral, ..." "长安月:..." "心跳节拍:..."`
  支持 `--ai 主题` 用 LLM 自动生成 tags，支持 `--wait` 等完成。
- **撤销 `voxsuno batch`** `commit ce30a78`：之前的实现绕过了 voxflow 项目
  自身，直接调外部 suno CLI —— 与「自动化集成进项目」原则冲突，已 revert。

### 🎨 音乐封面模板落地

`templates/music-cover-prompt.md` + `scripts/gen_cover_prompt.py`：
24 个占位符 + 4 个 preset（治愈系傍晚 / 热血系正午 / 伤感深夜 / 抖音热门卡点）。
脚本**只产出 prompt + 打印 museav gen 命令**，绝不自动跑（花钱红线）。

### 🎵 全局播放器重做 + AudioBus 单音频协调

之前 GlobalPlayer 和 PersonaSidebar 各自有独立 `<audio>` 元素，
**同时点两首会叠加播放**。重构两件事：

- **`stores/audioBus.ts`**（新）：单例协调器，谁先 `play()` 谁占线，
  其他源自动 `pause()`。`activeChannelId` 响应式可订阅。
  PersonaSidebar 的 previewPlayer + GlobalPlayer 都注册成频道。
- **`components/player/CoverArt.vue`**（新）：黑胶唱片造型 —— 同心圆凹槽
  + 中心彩色标签 + 中心图标。颜色按 filename 哈希取一对互补色（djb2），
  每首歌不同；播放时 8s/圈慢转 + 外发光呼吸。
- **`components/player/SpectrumBars.vue`**（新）：28 根 CSS 动画 bar
  错峰（每根动画时长 + delay 都不同），纯 CSS 无 Web Audio API 开销。
  停止时全部归零高度。
- **`GlobalPlayer.vue`**（重做）：三栏布局 —— 左（CoverArt + 曲目）｜
  中（光谱条 + 进度条）｜右（大播放按钮 + 音量 + 操作）。大播放按钮
  白底圆 44px，播放中变紫发光 + hover scale(1.08)。最小化浮窗 60×60
  黑胶唱片 + 右下 mini 光谱条。键盘可达保留（方向键 / Home / End /
  空格）。
- **`PersonaSidebar` previewPlayer** 在 MainLayout 注册到 audioBus，
  `@pause` 事件清掉 UI 状态 —— 切换源时两边 UI 同步。

---

## [0.6.0] - 2026-09-12

### 🔌 甩掉 suno CLI：音乐生成改直连 Suno API

- **起因是被迫的**：2026-09-11 Suno 服务端强推 v6，老模型一律 403
  `paid_upsell`（"Please switch to v6!"），而 `paperfoot/suno-cli` 0.9.0 的
  `--model` 枚举最高只到 v5.5、上游 2026-07-20 起没再更新。等它 = 功能永久坏着。
- **`core/suno_api.py`（新）** 接管全部五个子命令：`generate` / `credits` /
  `list` / `status` / `cover`。`web/app.py` 里 `SUNO_BIN` 归零，
  `/api/suno/status` 现在报 `backend: direct-api`。
- **模型代号是挖出来的，不是猜的**：API 收的是 `chirp-hawk` 这种随机代号
  （v5.5=`chirp-fenix`、v5=`chirp-crow`），命名毫无规律。做法是把 suno.com
  首页的 99 个 JS chunk 全下下来，从 `[ModelTier.V6]:"chirp-hawk"` 那段
  原始映射里读出来。文件头记了下次怎么重新挖 —— 这是唯一会过期的东西。
- **认证自持，不再需要 `suno login`**：Clerk 两层凭据，`__client`（~7 天）
  是身份、JWT **约 1 分钟就过期**。所以「登录一次能一直用」靠的是每次调用前
  自动换 JWT，不是把 JWT 存下来。凭据存 `~/.voxflow/suno.json`(0600)，
  首次从 CLI 的 auth.json 导入一次，之后 CLI 删掉也不影响。
- **hCaptcha 借 browser-harness，没抄那 958 行**：`/api/c/check` 说这个账号
  `required: true`，纯 HTTP 拿不到 token。suno-cli 为此写了 958 行 Chrome
  生命周期管理 + headless 反检测，而项目里 browser-harness 附着的就是日常
  那个 Chrome，实测 8 秒出 token。
- 三个照抄源码会踩的坑，都已修并写进注释：按 id 查是 `/api/feed/` **不是**
  `feed/v3`、响应体**直接是数组**、一次最多 2 个 id；`feed/v3` 的空字段必须
  **整个不发**，发 `null` 直接 422。

### 🧹 删掉 380 行死代码

- `web/app.py` 里 `_run_suno_task` 和 `_recent_clips_titled` 各**定义了两次**，
  Python 只有后一份生效 —— 前面约 180 行是死的，而且两份内容**不一样**，
  意味着某次改动很可能改在了不生效的那份上。
- `_suno_env()` 和 `_clear_stale_solver()` 一并删除：它们唯一的存在理由是
  给 suno CLI 找 Chrome、清残留验证码进程，直连之后没这需求了。

### 🖥 `scripts/make-app.sh`（新）

生成 `~/Applications/VoxFlow.app` —— 双击启动后端并开一个无地址栏的窗口。
不是桌面版，也不替代 `docs/DESKTOP_APP_PLAN.md`：那份计划解决「别人怎么装」，
这 60 行只解决本机自用的「不想开终端、不想记 8866」。后端已在跑就直接开窗，
不重启 —— 那进程加载着 8.4G 模型，幂等不等于可以随便重跑。

### 🔑 AI 文案改走应用授权，不再借用租户 Key
- **租户模型对 VoxFlow 是错的**：`run.sh` 原来注入一把 voxcraft **租户** Key，
  含义是「应用方持 Key、花应用方的池子」—— 但 VoxFlow 装在用户自己机器上，
  该花用户自己的积分、产出归用户自己。租户 Key 还只能整把吊销，
  事后查不出哪次调用是哪个工具发的。
- **`core/museav_auth.py`（新）** 设备码授权，凭据存 `~/.voxflow/museav.json`
  并 `chmod 600` —— 默认 644 会让同机其它用户读到这把 Key。撤销后再调用拿 401，
  直接清掉废凭据并提示重新 login，不留一把每次都失败的死 Key。
- **凭据来源改成三档实时解析**（`core/llm_client.py` 的 `resolve_backend()`）：
  环境变量 > 应用授权 > 本地 FreeLLMAPI。**每次调用重新解析**，因为授权状态会在
  运行期变化（可能刚 login，也可能刚在中台撤销）；原来是 import 时求值的模块常量。
- 新命令 `voice museav login / status / logout`。

### 🎬 宣传片与封面提示词
- **`core/promo.py` + `voice promo`**：接入 reel-kit，音乐卡片宣传片自动合成；
  `PublishTab` 加入口，`scripts/auto_publish_ep.py`、`auto_publish_pure.py`、
  `publish_qishui_e2e.py` 补齐 EP / 纯音乐 / 汽水端到端脚本。
- **`templates/music-cover-prompt.md`**：24 个占位符 + 4 个 preset
  （治愈系傍晚 / 热血系正午 / 伤感深夜 / 抖音热门卡点）。之前提示词是 ad-hoc 写的，
  每次重头想灯光和避免清单，质量飘忽。
- **`scripts/gen_cover_prompt.py` 只产出 prompt，绝不自动跑 `museav gen`**，
  `--show-museav-cmd` 也只打印不执行 —— 花钱的那一步留给人手动确认。

### 📐 桌面版落地计划（文档，未动工）
- **`docs/DESKTOP_APP_PLAN.md`** 拍板两件事：① 拆两个构建，外壳 Tauri + Python
  sidecar，发布版 ~60 MB（不含 torch/模型）、完整版 ~2.2 GB；② lark-cli 与 museav
  改直连 HTTP，发布版不再要求装 Node。
- 拆得动的依据是实测：整条发行链路（pipeline / notify / r2 / net / cover / db / obs）
  对 torch / transformers / librosa / soundfile 的**引用数是 0**，
  `web/app.py` 的 `import torch` 已在函数内部（329、365 行）—— 不装 torch 服务照样起得来。
- 文档区分「实测」与「待验」，标待验的不要当已知。
- SOP 修订两处：声音设计 SOP 只管怎么念、文字方法指向 talk-skills。

---

## [0.5.0] - 2026-09-06

> 42 个提交，62 个文件，+7686 / −1090。主题是**把「歌做完了」到「歌上架了」
> 这一段真正跑通** —— 0.4.0 之前这条链路是断的。

### 🚀 自动化发布：从贴一个链接到停在提交前
- **新屏 `IntakeTab`（自动化发布）**：贴一条音频链接就能入库、出封面、备料。
  分成两条路 —— A「别人给我一个链接」不需要 Suno 账号也不需要下 7 GB 模型，
  B「歌是我自己生成的」直接去 AI 音乐屏，产物自动进发歌记录。
- **「发布中」不再是死状态**：点按钮真的拉起浏览器填表，不是改个状态字段完事。
- **补上登录环节**：选平台 → 登录 → 回填账号 → 才允许发布。
  以前跳过登录直接填表，失败原因看不出来。
- **汽水音乐实测跑通全流程**（《破晓》已提交审核）：填表改用 `insertText`
  （直接 set value 前端框架收不到事件）、填完自动截图扫红字、
  **结束后明确提示停在提交前** —— 最后一下由人点。
- 发布前置检查 + 两级导航；修「导入重复建曲目」。

### 📒 发行台账：一歌一链一行，可重跑
- **`core/r2.py`（新）**：本地音频一键传 R2 拿公网直链并回填台账。
- **`core/notify.py`（新）**：生成完推飞书群卡片（带源链接）+ 同步多维表格台账，
  幂等可重跑。修「群通知先看台账」—— 审核中的歌不再被喊成生成失败。
- **平台上架记录按 `song_id` 挂到 Suno 原曲**，支持改名和拆分；
  歌名对不上时**用时长认原曲**（Suno 上改的名从不同步下来，这是看板显示重名的真因）。
- **独家授权一首只能投一个平台，发行歌名必须唯一**（数据库约束，不靠界面拦）。
- 补平台 `song_id` 时改原记录，不另插一条。

### 🎨 封面出图与 Suno
- **封面改走 `museav gen`（业务中台 CLI），短边不够再本地 `museav upscale` 超分**，
  任务条显示真实进度。
- **Suno 异步的事按异步做**：提交拿 id、轮询状态，不再阻塞等；
  云端生成记录可同步下来（`scripts/sync_suno.py`）；声音克隆支持直接录音。
- 修 `voxsuno`：**CLI 报错 ≠ 没生成**（照样扣积分，得去查）；单价 10 → 70。

### 🧱 收敛与红线
- **平台清单归一到 `configs/platforms.json`**，网络绕坑逻辑收进 **`core/net.py`（新）**。
- **`core/version.py`（新）**：比 commit 不比 tag 判断版本落后（这个项目改得勤、
  很少打 tag，只看 tag 会永远显示「已是最新」）；拿不到远端信息时返回 `unknown`
  而不是假装最新。
- **`CLAUDE.md`（新）立红线：花额度的命令跑之前必须先问**。
  写这条的直接原因是拿出图请求做部署探测白烧了钱。
- 日志保留 14 天 → 3 天；清掉误入仓库的验证截图。
- 新增测试：`test_notify` / `test_r2` / `test_pipeline_accounts` /
  `test_pipeline_exclusive` / `test_pipeline_listings`。

### 🐞 三个「看起来像数据丢了」的界面故障
- **主内容区被整体隐藏**，八个屏全看不见 —— 像整屏黑屏。
- **音色试听和资产库都点不响**（两处播放全哑）。
- **前端重新构建后老页面点 tab 变空白**，看起来像数据没了，其实是旧产物还挂在页面上。

---

## [0.4.0] - 2026-09-05

### 📊 运营台：成本、收益、健康、日志（Observability & Unit Economics）
- **计量层 `core/obs.py`**：一次上游调用既是事件也是开销，统一在一处记录。
  结构化日志落 `~/.voxflow/logs/*.jsonl`（14 天滚动），计量落 SQLite
  `usage_events`（永久，可按作品/上游/月份聚合）。
- **成本按写入时单价定格**：换套餐、中台调价都不会回溯改写历史账目。
  单价表 `configs/pricing.json` 可被 `~/.voxflow/configs/` 覆盖。
- **失败的调用照样记账**：Suno 生成失败一样扣积分，只记成功的话账永远对不上。
  失败调用同时升级为 `error` 级日志 —— 它是筛 error 时最该第一个看到的东西。
- **收入侧接入**：从平台后台的累计播放量和可提现金额**反推实测千播单价**，
  比公开资料的区间中位数准；界面明确标注「实测」vs「估算」，
  分成率无一手资料的平台留空而不是填猜测值。
- **「本地跑省下多少」**：本地 TTS 的量 × 对标商业 API 单价 − 实付。
  免费的东西不算出来就没人感知得到。只按成功的量算 —— 失败不能算成收益。
- **新端点**：`/api/health`（三档深度体检）、`/api/metrics`（P50/P95 + 错误率）、
  `/api/logs`、`/api/economics`。
- **新界面**：`/#/ops` 运营台，三个分区（这门生意 / 系统健康 / 运行日志）。
- **新命令**：`voice stats`（`--tracks` / `--json`）、`voice logs`。

### 📈 收入拆到单曲：这门生意最该看的那张表
- **`scripts/ncm_track_stats.py`**：从网易云音乐人后台数据中心抓**单曲**播放量
  （切近 30 日、翻页、按标题回填台账）。已实测跑通：33 首全部匹配，零漏。
  公开 API 这条路先验证过是死的 —— `song/detail` 的 `playedNum` 恒为 0。
- **`track_platforms` 加 plays / earned_cny / stats_at**，`/api/economics` 的
  作品表随之给出 **成本 · 播放 · 折算收益 · ROI · 回本还差多少次**。
- **不做按比例分摊**。用账号总收益按播放占比摊到单曲，算出来的数看着合理，
  但它只是「总收益 ÷ 首数」的变体，回答不了「哪首值得再做一首同风格的」——
  而那是要它的唯一理由。现在的折算是「**真实单曲播放量** × 实测千播单价」，
  性质不同，且界面明确标注是折算不是平台实付。
- **null 和 0 严格分开**：「—」是还没抓数据，「0」是真的没播。混在一起会让
  「没同步」被读成「没人听」。

### 🎨 UI：图标语言收敛成一套
- `Icon.vue` 的文件头一直写着不用 emoji 的理由（三套系统渲染完全不同、
  不能跟主题变色），但老屏幕（克隆 / 设计 / 剧本 / AI 音乐）的表单标签
  **全是 emoji** —— 同一个产品里两套图标语言。31 处标签 + 6 处元件位一次换净，
  补了 9 个图标，对齐规则写在 `main.css` 里**一次**而不是五个组件各写一遍
  （那正是当初 emoji 能散开的原因）。我自己写的 OpsTab 也在其中。
- `scripts/smoke.py` 加了防回归断言，挡住 emoji 再混回 UI 元件位。

### 🚪 首次体验：从「一屏死路」到「打开就能用」
- **🐞 修了最致命的一个**：`install.sh` 把 7 GB 模型下到项目目录 `./models/`，
  而运行时按 `core/paths.py` 去 `~/.voxflow/models` 找 —— 新用户老老实实跑完
  安装、下了 7 GB，打开界面还是「模型未就绪」，且完全看不出为什么。
  （数据从项目目录搬到 `~/.voxflow` 那次改造漏改了这里。）现在直接问
  `core.paths.MODELS_DIR` 要路径，并把项目目录里的旧模型**搬过去而不是重下**。
- **健康检查不再把「没下模型」判成 down**。全新安装打开就看到红色「有项目坏了」，
  而那恰恰是正常状态。现在是 `degraded` —— 语音合成不可用，别的照常。
- **首屏按能力决定落点**：模型没下时落在「AI 音乐」（Suno 就绪即可用），
  而不是一整屏灰按钮的「声音克隆」。只对默认落点生效，显式访问 `/#/clone`
  一律尊重，老用户的书签不受影响。
- **界面里就能下模型**：`POST /api/models/download` 起后台子进程，
  进度实时显示（进度读取的后端一直都有，缺的只是触发入口）。幂等 ——
  连点两下不会下两份 7 GB；关掉页面也不中断。
- **新组件 `ModelSetupCard`** 替换三处「请回终端运行 ./install.sh」的警告条。
  它多做一件原来没做的事：**列出这期间照常能用的功能并可直接点过去**。
  只讲「你缺什么」是把人挡在门外，讲「这些不用等」才是让他马上能开始。

### 🖼 封面出图接入 museav 中台（ROADMAP #2 完成）
- **`core/cover.py`**：`POST /api/generate` → 轮询 → 下载 → 回填台账 `cover_file`。
  走 HTTP 直调而不是 museav CLI —— CLI 的 README 明确说产品集成走 HTTP。
- **计费：一张 1 积分**。单价（元/积分）在 `configs/pricing.json`，按实际买的
  积分包填；原来那个 0.05 的占位值低估了 16 倍，已改成 0.83。
- **不要传 `quality: "high"`**。一开始传了，**纯亏一倍**：传 high 扣 2 分、
  不传扣 1 分，而**出来的图尺寸体积完全一样**。quality 是画质参数、不控制
  尺寸，而中台不传时本来就按高画质出。这个默认值还漏改过一处 —— 改了
  `cover.generate()` 却没改 `CoverRequest`，**一个默认值分散在两处，
  只改一处就是这种下场**。
- **比例完全可配，不限枚举**。`ratio` 支持任意 `W:H`（含小数比例如 1:2.1）——
  中台本来就能传任意尺寸，CLI 帮助里那个五选一只是常用值提示，写死枚举等于
  把上游能力阉掉一半。看板顶栏用 `<input list>` 而不是 `<select>`，正是为此。
  格式写错在提交时 400 挡掉，不丢进任务队列再失败。
- **尺寸达标**：`1:1 → 1440x1440`（汽水要 ≥1440、网易云要 ≥1400，一张两边都够）。
  中台按 ratio 自动算的尺寸是保守的，所以显式传 size；比例太极端算不出来时
  回落到只传 ratio —— 宁可拿张小的，也别出不了图。
- **出图后核对实际画幅**。上游偶尔会把非方比例出成方图（实测过一次，同参数
  复测多次都是遵守的 —— 正因为偶发，人工抽查抽不到）。容差 5%：放过 1~2px 的
  正常取整，抓住把长图出成方图的。不符时结果带 ⚠️ 提示并记一条 warn 日志 ——
  图是好图只是画幅不对，不重试也不报错。`null`（量不出来）和 `false`
  （确认不符）严格分开。
- **额度：自家租户不该被闸门卡**。余额 0 却被拦住，那是中台侧的问题、
  **不是「该充值」**；已在那边修掉并新增了「受不受额度限制」的字段，
  VoxFlow 据此判断而不再只看余额 —— 自家租户余额恒为 0 而出图正常。
- 出封面按钮只在**缺封面**的曲目上出现：已有封面的再放一个，唯一作用是误点烧钱。
- **`tests/test_cover.py`**：25 条断言，覆盖比例白名单反模式、格式校验、画幅
  核对的容差边界（用的是真实实测值）。已进 CI。

> 中台的内部实现（计价怎么算、哪个上游在跑、哪次迁移改了什么）不记在这里 ——
> 抄过来只会在它改动后变成过时的假信息。要查的话分两层：规则在
> `museav-manager` 仓库，运行时状态（上游启用情况、租户额度、每单参数）
> 在数据库里、仓库中查不到。详见 `core/cover.py` 文件头。

### 💰 历史成本回填与估算标记
- **`voice backfill-costs`**（默认预演，`--apply` 才写）。判据是
  **有 clip_id = 确实调过 Suno**，这是硬证据；从平台同步回来的 31 首老作品
  不会被误回填。已回填 7 首合计 ¥2.03。
- **`usage_events.estimated` 列**：回填的每一条都带标记，CLI 和看板单独标出
  「其中 ¥X 是回填估算」。不区分的话，回填一次之后就再也分不清哪些数字是实测的，
  而分不清的数字最终会被当成实测的拿去做决策。撤销只需
  `DELETE FROM usage_events WHERE estimated=1`。
- `core/db.py` 加了轻量的增量迁移清单（`_ADD_COLUMNS`）—— 五张表、迁移全是加列，
  不值得引入一套 migration 框架。

### ⛔ TTS provider 可插拔：核实后判定前提不成立，暂不做
ROADMAP #1 写的「云端上游（比如中台已有的 TTS 通道）」——**中台没有这个通道**：
`shared/mimo-audio.js` 只有协议层且自己标着「尚未接线」，计费表里也没有 audio
档位。现在抽 provider 接口等于为一个实现造一层抽象。判断与先决条件已写回
`docs/ROADMAP.md`，等中台把 audio 链路接完再说。

### 🔧 其它
- **版本号收敛到 pyproject.toml**：此前 `web/app.py` 里硬编码了三处
  （FastAPI title / 启动日志 / 中台 User-Agent），发版改一处漏两处，
  日志里写着 0.3.0、接口文档写着 0.2.0。前端同理，`CLIENT_VERSION` 改由
  vite 从 `package.json` 注入，不再靠注释提醒人手工同步。
- **`env.d.ts` 的全局声明**：这个文件有顶层 import，是**模块**不是全局脚本，
  `declare const` 必须写在 `declare global` 里才全站可见。顺带补上了
  `window.$message` / `$dialog` 的类型 —— 之前缺这份声明，任何 .ts 里用它
  都要 `as any` 绕过去。
- 失败提示的措辞按 provider 实际是否扣费区分：一律说「照样扣费」会把
  「上游挂了」误导成「你亏钱了」，两者该采取的行动完全不同。

### 🐞 修复（两个影响面很大的问题）
- **Web UI 全部接口失效**：`ky` 从 1.x 升到 2.x 后 `beforeRequest` 改成收单个
  state 对象，而调用点仍按 `(input, options)` 写、并用 `as unknown as` 把类型
  强转掉了 —— 于是**每个请求都在 hook 里抛 `undefined.headers`**，界面全空
  而编译期一声不吭。已改为 ky 2.x 签名并去掉强转。
- **慢请求冻住整个服务**：42 个端点写成 `async def` 却在里面跑同步阻塞调用
  （LLM 几十秒、suno CLI 十几秒、SQLite、文件 IO），冻住事件循环。已改回普通
  `def`（FastAPI 自动走线程池）。随之 worker 从 2 回到 1 —— 任务队列和指标都在
  进程内存里，2 个 worker 就是两份互相看不见的状态，任务会在界面上忽隐忽现，
  而且 4GB 模型被加载两遍。

### 🧪 质量护栏（此前为零）
- `tests/test_obs.py`：11 条断言，覆盖单价定格、失败不算收益、未知分成率不猜数、
  日志级别过滤、计量永不抛异常。无框架依赖，`python tests/test_obs.py` 直接跑。
- `scripts/smoke.py` 增补可观测性四端点与健康语义断言（26 项全过）。
- `.github/workflows/test.yml`：CI 跑计量自检 + 前端 typecheck/build。
  类型检查是「升级后运行时全挂、编译期一声不吭」这类问题唯一的防线。

---

## [0.3.0] - 2026-08-30

### ✨ 核心特性与架构升级 (Features & Architecture)
- **平台维度信息架构与发行中枢 (Publish Hub)**：
  - 新增歌手身份台账（`configs/artist.json`），维护艺名（月栖洲）、真实姓名及各平台歌手 ID。
  - 支持自动提取与校验 **汽水音乐、QQ 音乐、网易云音乐** 平台已上架歌曲 ID 与播放外链。
  - 新增专辑实体管理、发行数据本地持久化与敏感信息界面脱敏。
- **纯净精密声学设计系统 (Precision Dark UI)**：
  - 彻底净化杂色污染与弥散大光斑，确立纯黑精密灰阶与 100% 对比度冷白排版体系。
  - 发丝级 `1px` 微边框与清晰几何层次，兼具现代音频 Studio 与专业生产力工具质感。
- **高阶液态毛玻璃音乐播放器 (Liquid Glassmorphism Player)**：
  - 深度定制全自定义音频播放底栏，集成 `backdrop-filter: blur(32px)` 液态毛玻璃与顶部棱镜高光。
  - **冷光流动渐变进度条**：播放时激活冷光流光扫描动画，搭配高精度拖拽定位与双层冷光滑块（Thumb）。
  - **实时声波律动指示器**：播放音频时自动激活 4 柱动态均衡器跳动脉冲。

### 🛠️ 工程与类型优化 (Engineering)
- **TypeScript 强类型重构**：前端核心 `pipeline.ts` 迁移至 TypeScript，新增完整的 API 接口数据契约类型定义。
- **FastAPI 静态资源与并发优化**：多 Worker 模式支持，避免长时间任务阻塞状态轮询；生产静态产物自动化对齐与无缓存策略。
- **全新真实工作台截图与文档**：全量更新 [README.md](README.md) CLI 命令体系与最新高清 UI 界面截图。

---

## [0.1.1] - 2026-02-28

### 💥 Breaking Changes
- **移除播客模式**：删除 `PodcastMode`，主流程不再支持播客分支派发。
- **统一输出目录**：所有成品统一输出到 `assets/output_audio/`。
- **配置收敛**：运行态配置收敛为 `clone.json`、`design.json`、`dialogue.json` 与 `personas.json`。

---

## [0.1.0] - 2026-02-27

### ✨ 核心特性 (Features)
- **模块化集群架构 (V2)**：重构项目结构，严格隔离克隆、设计、对话三大模式。
- **Apple Silicon 原生加速**：针对 M1/M2/M3 芯片深度优化，引入 MPS 硬件加速与 SDPA 注意力机制。
- **对话剧场模式**：支持多角色台词连续生成，并自动进行场景缝合与呼吸感处理。
- **AI 样音自动化**：内置 Ref-Opt 组件，支持 1.5s 安全避障裁剪、物理脱水去噪及无损 WAV 格式归一化。

---
*雪落江湖，热血难凉。*
