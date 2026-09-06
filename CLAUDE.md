# VoxFlow —— Agent 红线

## 🔴 花钱的命令，跑之前必须先问

**这个项目里每一次生成都在花真钱**，而且额度是有月度上限的、用掉不可逆。

以下命令**一律先征得同意再跑**，禁止以「验证一下」「端到端测试」「顺便确认」
为由自行执行：

| 命令 / 端点 | 花什么 |
|---|---|
| `suno generate` / `describe` / `cover` / `extend` / `remaster` / `concat` / `stems` | Suno credits（月度上限，用完要等下个月） |
| `POST /api/suno/generate`、`/api/suno/batch`、`/api/suno/cover` | 同上（它们就是在调上面那些） |
| `POST /api/cover/generate`、`museav gen`、中台 `/api/generate` | museav 积分 |
| `POST /api/llm/*`、`/api/trending` | LLM token |

**免费的可以随便跑**：`suno list` / `credits` / `status` / `info`、
`suno write` / `lyrics`（CLI 明说不花积分）、以及所有只读端点
（`/api/health`、`/api/metrics`、`/api/economics`、`/api/suno/clips`……）。

### 想验证功能怎么办

按这个顺序，**前三条都不花钱**：

1. **看参数校验** —— 传非法入参看是不是按预期 400（`{"clip_id":""}` → 400）
2. **看只读端点** —— `/api/suno/clips` 能列出库、`/api/cover/status` 能报能力
3. **看代码路径** —— 单测、`--help`、CLI 的 dry-run
4. 确实需要真跑 → **停下来问**，说清楚要花多少、为什么非跑不可

### 已经犯过两次，都是同一个借口

- 2026-09-05：用**出图请求**做 Cloudflare 部署探测，白烧 2 张图（¥1.66）。
  正确做法是查部署 API，零成本。
- 2026-09-06：为「端到端验证翻唱功能」，擅自拿用户的真实作品跑了一次
  `suno cover`。用户没要求测，生成的东西他也不要。

两次都是**把「我想确认它能跑」当成了花用户钱的正当理由**。它不是。
功能写完告诉他怎么验证，由他决定什么时候花这个钱。

## 其它

- **数据在 `~/.voxflow`，代码在项目目录**（见 `core/paths.py`）。
  经营数据（收益、播放量）不写进 git —— 它们在 `voxflow.db` 和运营台里是实时的，
  写进文档就是必然过期的快照。
- **封面自己出**：走 `museav gen`（业务中台 CLI），短边不够再本地 `museav upscale`。
  不要拿 Suno 360 图交差，不要只超分一张别人的图当新封面。
  `museav gen` 仍花积分，验证功能不许拿真出图当探测。
- **中台的内部实现不抄到这里**。voxflow 是调用方，只记「接口怎么用、多少钱」。
  要查中台注意分两层：规则在 `museav-manager` 仓库，运行时状态（上游启用情况、
  租户额度）在数据库里、仓库中查不到。详见 `core/cover.py` 文件头。
- **改前端后跑 `npm run check`**（typecheck + build 两步都要）。
  只跑 typecheck 漏过真 bug —— 重复 import 只有 build 会报。
- **验证 UI 要看图，不能只读 DOM**。`display:none` 的节点 `querySelector`
  照样找得到，「在 DOM 里」≠「看得见」。2026-09-06 的整屏黑屏就是这么漏过去的。
