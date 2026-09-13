# 数据存在哪

一句话：**台账在 SQLite（`~/.voxflow/voxflow.db`），配置和文件资产还是 JSON + 目录。**

| 放什么 | 在哪 |
|---|---|
| 作品台账、平台状态、专辑、事件流水 | **`voxflow.db`**（7 张表） |
| 配置：艺人档案、平台清单、音色库、账号 | `configs/*.json` |
| 文件资产：参考音频、合成产物、发布物料 | `assets/` `out/` `publish/` `library/` |

---

## 为什么后来还是上了数据库

这份文档原先写的是「全是 JSON 文件，没有数据库」，并且论证了在几百首的规模上
加数据库是纯负债。那个判断在当时成立，**后来被三件事推翻了**——正好就是当初
自己定下的那三条换库标准：

1. **需要查询了**。「哪些歌在汽水是 online 但还没回填播放量」这种问题，
   全读进内存过滤能做，但每加一个维度就多一层循环。SQL 一句话的事。
2. **需要并发写了**。后端任务队列会并发改台账（出封面、同步平台、批量生成同时在跑），
   `_load → 改 → _save` 全量重写必然互相覆盖。
3. **一首歌对多条平台记录**。同一首在汽水/网易云各有状态、各有 song_id，
   JSON 里嵌套三层之后就没法维护了。

所以现在是：**结构化、会并发、要查询的进库；单纯的配置留 JSON。**

> 教训记在这儿：这份文档从 JSON 迁到 SQLite 之后**很久没同步**，
> 开头那句「没有数据库」误导过读它的人（和 agent）——
> **过时的架构描述比没有文档更糟，因为它让人从错误的前提开始推理。**

---

## 台账：`voxflow.db`

```
tracks              作品本体：标题、歌词、风格标签、clip_id、音频/封面路径、
                    stage（draft→generated→selected→publishing→published）、
                    release_title（发行名，全局唯一）、release_platform（独家授权）
track_platforms     一首歌 × 一个平台的上架记录：status、song_id、song_url、
                    album_id、track_no、plays、earned_cny、publisher
albums              专辑：本地草稿（album_id 形如 local-xxxxxxxx）与平台同步回来的
publish_events      状态流转事件流：什么时候从哪到哪、谁操作的
platform_accounts   各平台账号资产与登录状态
usage_events        调用流水与计费：Suno / LLM / museav 各花了多少
meta                schema 版本等元信息
```

看表结构直接 `sqlite3 ~/.voxflow/voxflow.db ".schema tracks"`，
读写一律走 `core/pipeline.py`，**不要在别处手写 SQL** —— 独家授权、发行名唯一、
专辑发行后不可增删这些规则都在那里，绕过去就等于绕过规则。

---

## 配置：`configs/*.json`

这些是**配置不是台账**，改动低频、要人读人改，留 JSON 正合适：

- `artist.json` — 艺人档案（含实名信息，接口返回时会脱敏）
- `platforms.json` — 平台清单：后台地址、发布入口、触达范围、核验日期
- `pricing.json` — 各平台单价口径（标了 confidence，未证实的写 0 不猜）
- `personas.json` — 音色库：每个音色的参考音频与设计配方
- `publish_accounts.json` — 平台账号占位；真正的登录态在浏览器里
- `notify.json` / `r2.json` — 飞书通知与图床配置

### 其余

- `scripts.json` — 存过的配音文案
- `design.json` / `dialogue.json` — 音色设计和多角色对话的配置模板

---

## 文件资产：三层，按**生命周期**分

不按类型分（音频/图片），按「丢了会怎样」分：

| 目录 | 性质 | 丢了会怎样 |
|---|---|---|
| `assets/` | **不可再生** | 参考录音没了就没了，音色再也复刻不出来 |
| `out/` | **可再生** | 合成产物、下载的歌，删了重跑就有 |
| `publish/` | **平台规定** | 结构是平台要求的，不能按自己的想法整理 |

具体：

```
assets/
  temp/               当前参考样音（personas.json 的 ref 指这里）
  reference_audio/    原始录音素材
out/
  clone/ design/      TTS 合成产物
  music/              Suno 下载的歌 ← 浏览器下载目录直接指到这里，点一下就入库
publish/
  templates/          平台的 Excel 模板（收在项目里，不放 ~/Downloads——那儿随时会被清理）
  YYYYMMDD/<歌名>/    发布物料：Audio/ 歌词/ Cover/
voice_designs/        音色设计配方（personas.json 的 design 指这里）
```

**目录可以重排，资产不能删。** 觉得目录不合理就转移资产，不是删掉重来。

---

## 云端同步（音频资产）

音频 + 封面同步到 R2 已经落地：`scripts/sync_r2.py`。

对每首**本地有音频**的作品上传到 music 桶：

```
masters/<year>/<slug>/master.wav   母带（优先同目录 .wav，只有 mp3 就用它）
masters/<year>/<slug>/cover.jpg    封面（有就传，保留原扩展名）
masters/<year>/<slug>/meta.json    元数据（版权链凭证）
```

上传成功后 `cloud_backup` 写成 `{status: "backed_up", location, updated_at}`，
location 是 R2 key 前缀。`--dry-run` 只看不传，`--public` 额外镜像
`public/<slug>.<ext>` 对外播放版（默认不传 —— 母带目录是备份真源，
public 需要时从母带重建即可）。

凭证走 `cs kyvault get secret://cloudflare/api-token`（或 `CF_API_TOKEN`
环境变量），桶 `music`、公开域名 music.webkubor.online —— R2 的位置和分类
以 CortexOS 的 `cs resource policy` 为真源（r2 是当前主力，picx 已冻结新增）。

**台账本身（voxflow.db / configs）还没进 R2**，见 docs/TODO.md #4。

---

## 备份

`configs/*.json` 里 `personas.json` 和 `pipeline.json` **在 .gitignore 里**——
那是个人数据，不该进公开仓库。所以它们目前**没有任何备份**，
这也是要做 R2 同步的原因之一。

音频资产同理：`out/` 和 `assets/` 都不进 git（太大）。
