# 从小白到唱一首歌 · 全链路 SOP

> 2026-09-12 实测重写。每一步都跑过，**没跑通的地方明确标出来**，不写「理论上可以」。
>
> 已有的两份入门文档仍然有效，这份负责把它们串起来，并补上
> 「用自己的声音」「翻唱自己的歌」「改名」「发布」这几段：
> - [做一首歌](新手指南_做一首歌.md) —— 怎么写风格标签和歌词（最该先读）
> - [发一首歌](新手指南_发一首歌.md) —— 平台侧怎么上架

---

## 零、先看懂两笔账，不然会白忙

这是最容易搞错、也最贵的一件事：**生成和下载是两笔独立的账。**

| | 花什么 | 现在的状态 |
|---|---|---|
| **生成**一首歌 | Suno credits | **v6 促销期内 0 消耗**（实测生成 14 首，`monthly_usage` 纹丝不动） |
| **下载**成可用音频 | 「20 首/月」下载配额 | 促销**不免**这个，用完要等下月 |

没解锁下载的歌，拿到的 `media_urls` 是 **`m4a-opus` 流媒体格式**，
只能在 Suno 里在线听 —— **ffmpeg 都打不开，发行用不了**。

> 2026-09-12 的教训：库里 10 个 m4a 全是坏的（`file` 报 `data`），
> 根因就是走未解锁的流媒体地址下的。`clip.is_download_unlocked` 是 `False` 时，
> 下回来的一定是废文件，不要重试，重试多少次都一样。

**所以正确姿势是：促销期敞开生成 → 在 Suno App 里听 → 只给要发的那几首解锁下载。**

查额度（免费，随便跑）：
```bash
.venv/bin/python -c "from core import suno_api; print(suno_api.credits())"
```

---

## 一、路线图：你要哪一种？

| 你想要的 | 走哪条 | 现在通不通 |
|---|---|---|
| AI 唱一首原创 | **路线 A** | ✅ 全自动 |
| 用 AI 翻唱**我自己的**音乐 | **路线 B** | ✅ 今天刚打通 |
| 用**我自己的声音**唱 | **路线 C** | ⚠️ 中间一步必须手动 |

---

## 二、路线 A：生成一首原创（最简单）

后台（推荐）：打开 <http://127.0.0.1:8866> → 「音乐 · AI 音乐」→ 填标题、风格标签、歌词 → 生成。

批量（一次最多 20 首）：
```bash
./scripts/batch_bgm.py "长安雪:chinese traditional, guzheng, bamboo flute, 80 BPM" ...
```

要带唱就传歌词；**歌词留空自动变纯 BGM**（后端会自动补 `instrumental` 标签）。

风格标签怎么写 → 看[做一首歌](新手指南_做一首歌.md)，一条铁律：**写乐器名，别写心情**。

---

## 三、路线 B：翻唱我自己的音乐

Suno 的「翻唱」只认它自己库里的歌，**本地文件必须先传上去**换一个 clip_id。
这一步 2026-09-12 补好了（`core/suno_api.upload_audio`），上传本身**不花任何额度**。

```bash
.venv/bin/python - <<'PY'
from core import suno_api
# 1) 把本地音频传进 Suno（mp3/wav 直传，其它格式会自动转 mp3，需要 ffmpeg）
clip_id = suno_api.upload_audio("/路径/我的歌.mp3", title="我的原曲")
print("拿到 clip_id:", clip_id)

# 2) 用它翻唱 —— 换风格重新演绎（这一步在促销期同样免费）
clips = suno_api.cover(clip_id, tags="chinese folk, guzheng, female vocal, 90 BPM")
print([c["id"] for c in clips])
PY
```

`audio_influence`（0-100）控制原曲对结果的影响：**数值越高越像原曲**，越低 AI 发挥越多。

> 坑：Suno 的解码器挑食，m4a 经常报 `Source is corrupted` ——
> `upload_audio` 已经自动转 mp3 绕开了。但**源文件本身坏的救不了**，
> 传之前先 `file 你的文件.mp3` 确认它是真音频。

---

## 四、路线 C：用我自己的声音唱

完整链路是四步，**第 2 步目前必须在浏览器里手动做**（Suno 没有开放建音色的 API）：

| 步骤 | 在哪做 | 状态 |
|---|---|---|
| 1. 克隆你的声音，生成一段样音 | 后台首页「声音克隆」 | ✅ 自动 |
| 2. 把样音传到 Suno，建一个 Custom Voice | **suno.com 网页，手动** | ⚠️ 无 API |
| 3. 把拿到的 voice id 登记回本地 | `./voxsuno link <id> <名字>` | ✅ |
| 4. 用这个 persona 唱歌 | 后台「AI 音乐」选 persona | ✅ |

具体操作：
```bash
./voxsuno sample <你的音色key> "这是一段样音"   # 出样音并自动打开 Suno 建音色页
# ——（在网页上传样音，拿到 voice id）——
./voxsuno link <voice_id> 我的声音              # 登记
./voxsuno list                                  # 确认登记上了
```

> 现状：`~/.voxsuno/personas.json` 还是空的，**一个音色都没链接**，
> 所以后台「AI 音乐」里的 persona 下拉现在是灰的。要用路线 C，必须先走完上面四步。
>
> 第 2 步能不能自动化：clip 的 action 列表里确实有 `create_voice`，
> 说明后端有这个能力，但端点没找到（盲试 6 次全 404）。
> **要补就用 req 抓一次网页端建音色的真实请求**，别再猜。

---

## 五、改歌名（发行之前）

两个名字是**两回事**，别搞混：

| | 是什么 | 怎么改 |
|---|---|---|
| Suno 里的歌名 | 云端显示名，可以重复 | `suno set <clip_id> --title "新名"`（免费） |
| **发行歌名** | 上架到平台的名字，**全局唯一** | 后台改，或 `/api/pipeline/rename` |

发行名的规矩（`core/pipeline.py`）：

- **一首只能投一个平台**（独家授权，再投就是违约）
- **发行名全局唯一**，撞名直接拒绝
- **交到平台后台之前随便改；一旦 `uploaded` 就锁死** ← 2026-09-12 新增

```bash
curl -X POST http://127.0.0.1:8866/api/pipeline/rename \
  -H 'Content-Type: application/json' \
  -d '{"track_id":"<id>","release_title":"想好的名字"}'
```

已经提交到平台审核的会明确拒绝并告诉你卡在哪：
> `已经交到平台后台了，名字不能再改：汽水音乐（reviewing）。真要改得先去平台后台撤回。`

---

## 六、发布

状态流转：`draft → preparing → uploaded → reviewing → online`

- `preparing` = 本地备料中，**名字还能改**
- `uploaded` 起 = 已经交到平台后台，**名字锁死**

后台「发行 · 自动化发布」贴链接自动入库备料；「发歌记录」看谁发了什么、卡在哪。
平台侧的具体操作（汽水/网易云后台怎么点）看[发一首歌](新手指南_发一首歌.md)。

**发行前必须齐的三样**：可用音频（解锁下载过的）、封面、唯一的发行名。
封面走 `museav gen`（花积分，别拿 Suno 的 360 小图交差）。

---

## 七、把新生成的歌同步进本地库

在 Suno 网页端出的歌、脚本生成的歌，都靠这个补进本地曲库（**免费，随时可重跑**）：

```bash
.venv/bin/python scripts/sync_suno.py --dry-run   # 先看会新增什么
.venv/bin/python scripts/sync_suno.py             # 真的写库
```

只补不改：本地已有的歌词、发布状态、平台链接一个字都不动。

---

## 八、已知的坑（都是真踩过的）

| 现象 | 根因 | 怎么办 |
|---|---|---|
| 下回来的 m4a 打不开、`file` 报 `data` | 没解锁下载，拿到的是加密流媒体 | 先解锁下载，别重试 |
| 生成报「解验证码失败」 | hCaptcha 通道断了 | 已改走 ego-browser（2026-09-12 修） |
| 上传报 `Source is corrupted` | Suno 解码器不吃 m4a | `upload_audio` 已自动转 mp3；也要查源文件本身是否损坏 |
| persona 下拉是灰的 | 一个 Suno 音色都没链接 | 走路线 C 的四步 |
| 改名被拒 | 已交到平台后台 | 先去平台后台撤回 |
