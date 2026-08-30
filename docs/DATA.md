# 数据存在哪

一句话：**全是 JSON 文件，没有数据库。** 台账在 `configs/`，文件资产在
`assets/` `out/` `publish/` 三层。

---

## 为什么不用数据库

规模决定的。这是个单人本地工具，台账规模是**几十到几百首歌、几个到几十个音色**，
一个 JSON 文件全装得下。上数据库要引入三件事——迁移、连接管理、备份，
而在这个规模上它们一件都换不来收益。

JSON 还有三个此处很实在的好处：

- **可读**：出问题直接 `cat` 就能看，不用连库开客户端
- **可手改**：状态错了用编辑器改一行就行
- **可 diff**：进 git 之后，「这首歌什么时候从已选定变成发版中」在历史里看得见

### 什么时候该换数据库

不是「数据变多」，是**出现下面任一条**：

1. **需要并发写**。现在是单进程单人，`_load` → 改 → `_save` 全量重写没问题；
   多个进程同时写会互相覆盖。
2. **需要查询**。现在都是「全读进来再过滤」，几百条无所谓；
   到了要按时间范围、按平台状态组合查，就该上库了。
3. **单文件超过几 MB**。歌词是最大的字段，一首约 400 字；
   1000 首约 1.5 MB，还行。到几万首再说。

在那之前，加数据库是纯负债。

---

## 台账：`configs/*.json`

### `pipeline.json` — 作品台账（最重要的一份）

每首歌走到哪一步、内容是什么、发到哪了。结构见 `core/pipeline.py`。

```
tracks: {
  <track_id>: {
    # ── 流程状态 ──
    stage           draft | generated | selected | publishing | published | archived
    platforms       { qishui: {status, updated_at}, netease: {...} }   # 每个平台单独记

    # ── 创作元数据（必须留底）──
    title           歌名
    lyrics          完整歌词
    tags            送给 Suno 的风格串
    prompt          让 LLM 写歌词时给的描述
    voice           用了哪个音色（TTS 类作品）
    clip_id         选定的 Suno clip
    clip_ids        [两个]  —— Suno 一次出两首，另一首也留着

    # ── 本地产物 ──
    audio_file      out/music/xxx.wav
    cover_file      publish/.../cover.jpg

    # ── 云端（预留给 R2 同步）──
    cloud_backup    { status, location, updated_at }

    note, updated_at
  }
}
```

**为什么歌词要存台账而不是只留在 Suno**：Suno 那边不归我们，账号一停、
对方改版、清理旧作品，数据就没了。而歌词是平台发布的必填项，
风格标签影响推荐，出问题要复现也得靠它们。文件名更是只能塞下一个标题。

**为什么每个平台单独记状态**：同一首歌可能汽水已上架、网易云还在审核。
只有一个全局状态表达不出这种情况。

**状态机不做自动跃迁**：`generated → selected` 是「我要哪一首」，
`selected → publishing` 是「我确认发这首」。两个都是人的决定 ——
文件齐了不代表人想发。发版之前不该做任何平台相关的事，
因为不知道发哪个平台，封面尺寸和文案风格都定不了。

### `personas.json` — 音色库

```
<key>: {
  name          显示名，随便改（中文、空格、标点都行）
  ref           参考音频路径 ← 音频的唯一真源
  design        设计配方路径
  instruction   合成时给模型的基础指令（「怎么念」）
  desc          给人看的描述（「这是谁」）
}
```

⚠️ **路径只从 `ref` 读，绝不从 `name` 拼**。以前是按 `当前参考_{name}.wav`
拼路径，于是改个中文名音频就找不到，而且静默失败。现在 name 是纯粹的名字。
写入侧（新建样音）仍用名字起文件名，无所谓——落盘时会把路径记进 `ref`。

### `publish_accounts.json` — 平台账号状态

只存非敏感元数据（平台、登录状态、检测时间）。**不存 cookie、不存密码**。
真正的登录态在浏览器里，通过 browser-harness 附着使用。

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

## 云端同步（还没做）

`cloud_backup` 字段已经立好了（`{status, location, updated_at}`），
同步到 R2 之后往里写。字段先占位是为了**避免到时候改结构还要迁移已有台账**。

R2 的位置和分类走 `cs resource policy`（r2 是当前主力，picx 已冻结新增）。

---

## 备份

`configs/*.json` 里 `personas.json` 和 `pipeline.json` **在 .gitignore 里**——
那是个人数据，不该进公开仓库。所以它们目前**没有任何备份**，
这也是要做 R2 同步的原因之一。

音频资产同理：`out/` 和 `assets/` 都不进 git（太大）。
