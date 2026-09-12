# 文档索引

> 先看这里再找文件。2026-09-12 建 —— 在此之前 `docs/` 下十几个文件没有任何索引，
> 每次都要靠人提醒「项目里有 SOP」，agent 更是每次重新摸一遍。

**状态标记**：✅ 当前有效 · ⚠️ 部分过时 · 📋 计划/待评审（不代表已实现）

---

## 我要做什么？

| 我想… | 看这份 |
|---|---|
| 第一次做 AI 音乐，不知道从哪下手 | [新手指南_做一首歌](新手指南_做一首歌.md) ✅ |
| 歌做好了，想发到平台 | [新手指南_发一首歌](新手指南_发一首歌.md) ✅ |
| 用自己的声音唱歌 / 翻唱自己的音乐 | [SOP_从小白到唱一首歌](SOP_从小白到唱一首歌.md) ✅ |
| 发版前要遵守哪些硬规矩 | [MUSIC_PUBLISH_SOP](MUSIC_PUBLISH_SOP.md) ✅ |
| 发一个新版本（代码侧） | [RELEASE_SOP](RELEASE_SOP.md) ✅ |
| 忘了某个命令怎么敲 | [COMMANDS](COMMANDS.md) ✅ |
| 数据存在哪、表结构什么样 | [DATA](DATA.md) ⚠️ **已过时** |
| 接下来要做什么、为什么 | [ROADMAP](ROADMAP.md) ✅ · [TODO](TODO.md) ✅ |
| 克隆儿童声音时首字被吞 | [儿童声音首字保护指南](儿童声音首字保护指南.md) ✅ |
| 了解音频资产的产品设计 | [AUDIO_ASSET_CENTER](AUDIO_ASSET_CENTER.md) 📋 |
| 打包成桌面应用 | [DESKTOP_APP_PLAN](DESKTOP_APP_PLAN.md) 📋 |
| 封面出图的历史记录 | [COVER_IMAGE_LOG](COVER_IMAGE_LOG.md) ✅ |

根目录还有：[README](../README.md) · [CLAUDE.md](../CLAUDE.md)（**agent 红线，动手前必读**）·
[TECHNICAL_PATH](../TECHNICAL_PATH.md) · [VOICE_DESIGN_SOP](../VOICE_DESIGN_SOP.md) ·
[TUI_DESIGN](../TUI_DESIGN.md) · [CONTRIBUTING](../CONTRIBUTING.md) · [CHANGELOG](../CHANGELOG.md)

---

## ⚠️ DATA.md 已经和现实不符

它开头写着「**全是 JSON 文件，没有数据库**」，而实际上台账早就在 SQLite：

```
~/.voxflow/voxflow.db
  tracks · track_platforms · albums · publish_events · platform_accounts · usage_events · meta
```

`configs/` 现在只剩**配置**（platforms.json / pricing.json / artist.json），不是台账。
读 DATA.md 前先知道这件事，否则会照着它去找根本不存在的 JSON 台账。

> 这类错误的代价不只是浪费时间 —— agent 读文档比读代码更早，
> **一份过时的架构描述会让它从错误的前提开始推理**。

---

## 脚本在哪（`scripts/`）

| 要干什么 | 脚本 | 花钱？ |
|---|---|---|
| 把云端 Suno 作品补进本地库 | `sync_suno.py` | 免费，可随时重跑 |
| 对账网易云 / QQ / 汽水的真实状态 | `sync_netease.py` · `sync_qq.py` · `sync_qishui.py` | 免费 |
| 批量生成 BGM | `batch_bgm.py` | **花 Suno 额度** |
| 汽水发布（自动填表，停在签协议） | `publish_qishui_ego.py` | 免费 |
| 检查封面齐不齐 | `check_covers.py` | 免费 |

**同步脚本的通用原则：只补不改** —— 云端状态只用来补齐本地没有的，
本地攒出来的歌词、封面、收益记录一个字都不动。

---

## 给 agent 的三条

1. **动手前读 [CLAUDE.md](../CLAUDE.md)** —— 那里是花钱红线，跑错一条就是真金白银。
2. **遇到「这个表单/接口怎么用」，先搜 `scripts/` 里有没有人探过**，
   不要打开浏览器现场试。2026-09-12 发布那次，AI 声明怎么定位、
   下拉为什么要分两步展开，答案早就写在 `publish_qishui.py` 的注释里，
   却因为没读它而在页面上重试了七八轮。
3. **平台状态的真源在平台后台，不在本地台账。** 本地只是缓存，
   而且汽水那条线直到 2026-09-12 才有同步脚本 —— 之前全靠手记，错了没人发现。
