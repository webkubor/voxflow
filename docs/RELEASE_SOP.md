# 发版 SOP（Release Standard Operating Procedure）

> **修订日期**：2026-09-15
> **目的**：把「什么时候算一个发版版本」、「发版要做哪些动作」、「写什么进 CHANGELOG」
> 三个问题写死，避免每次靠记忆。
>
> 这是**软件发版**的 SOP（什么时候切版本号、推 git tag、CHANGELOG 怎么写）。
> 音乐平台发版流程见 [MUSIC_PUBLISH_SOP.md](./MUSIC_PUBLISH_SOP.md)。

---

## 一、什么时候发版

按下面任一条件触发（满足即发）：

| 触发条件 | 说明 | 示例 |
|---|---|---|
| **新模式/新流程上线** | 用户能感知到的「以前没有、现在有了」 | Suno 三模式、批量生成、错误日志 |
| **破坏性变更** | API 删除 / 行为反过来的 | suno CLI → 直接 API |
| **跨多个 Tab/Page 重构** | 视觉/交互范式改了 | UI 重做、token 统一 |
| **攒够 5+ commits** | 攒一波 | —— |

不触发发版的事（只在 [未发布] 里继续攒）：
- 修单个 bug（除非用户可见）
- 单文件小改
- 文档更新
- 内部清理（删死代码、refactor）

## 二、版本号规则（SemVer）

```
MAJOR.MINOR.PATCH

MAJOR  不兼容的 API / 工作流破坏（如 0.x → 1.x）
MINOR  新功能（默认）
PATCH  bug fix
```

**0.x 阶段**：MINOR 当主版本用，意味着「曾承诺过的最大变更」。

参考：
- `0.5.x → 0.6.0`：suno CLI 甩掉、重大内部清理
- `0.6.0 → 0.7.0`：UI 重做、批量生成、Suno 三模式 —— 本次该切

## 三、发版流程（10 步，10-20 分钟）

```
1.  拉最新代码
    git checkout main && git pull

2.  决定版本号
    - 看 [未发布] 里攒了多少项
    - 看是否有破坏性变更 → MAJOR
    - 看是否有新功能 → MINOR
    - 否则 PATCH

3.  打开 CHANGELOG.md
    - 把 [未发布] 内容原样移到 [X.Y.Z] - <日期>
    - 顶部留空的 [未发布] 段，给下一次攒
    - 修订日志顶部要保留「本项目遵循 SemVer」一行

4.  git tag
    git tag -a vX.Y.Z -m "vX.Y.Z: <一句话核心>"
    git push origin vX.Y.Z

5.  git commit CHANGELOG 改动
    git commit -am "chore(release): vX.Y.Z"
    git push origin main

6.  GitHub Release（可选但推荐）
    gh release create vX.Y.Z \
      --title "vX.Y.Z: <一句话>" \
      --notes "$(awk '/^## \[X.Y.Z\]/,/^---$/' CHANGELOG.md | head -50)"
    # 自动从 CHANGELOG 抓 [X.Y.Z] 段作为 release notes

7.  本地烟测（5 分钟）
    ./run.sh dev → 浏览器打开 → 跑一遍新功能主路径
    # 至少：UI 启动、生成一个音频、看板推进、全局快捷键

8.  通知本人（如果是个人项目，就是写进对话上下文）
    # 不是 GitHub release 那种公开通知，是「这事做完了」

9.  清 [未发布]
    已经在步骤 3 做了 —— 这次流程后，[未发布] 是空的或只有未完项

10. 归档本次发版用的 prompt / commit 记录
    # 写一句话进 docs/ROADMAP.md 底部「最近完成」
```

## 四、CHANGELOG 写作约定

每条**三件套**：
1. **标题**（动词+结果）：动词起头，不超过 60 字
2. **why**（背景/原因）：一段说「为什么做」，让后人理解决策
3. **what**（变更点）：bullet 列出实际改的东西

模板：

```markdown
### 🎯 <一句话标题>

<为什么做 —— 一段背景 / 决策理由 / 踩过的坑>

- <具体改动 1>
- <具体改动 2>
- <bug fix / 重构 / 文档>
```

**避免**：
- 只写「新增 X 功能」 —— 没有 why 就是 changelog 噪音
- 「优化」—— 没说什么优化了什么
- 「重构」—— 不说为什么重构
- 大段 git diff 复制 —— changelog 是给人看的不是给 git 看的

**emoji 前缀**（保持视觉一致）：
- 🎯 新功能
- 🐛 bug 修复
- 🧹 重构 / 清理
- 📚 文档
- 💥 破坏性变更
- ⚙️ 工程优化
- 🎨 UI / 视觉

## 五、什么时候不发版

不是每次 commit 都要发版。过度发版会：
- 用户每次都得升级 / 重新学习
- CHANGELOG 噪音大
- 失去「版本号有意义」的信号

**攒** vs **发**的判断：
- 一个独立 feature 改完用户能立刻用 → 可以单发
- 多个小改动攒一起 → 攒一波
- 改完了用户还看不到效果（仅内部清理）→ 攒

## 六、本次建议

按上面规则，**当前 [未发布] 段已经攒够一个 0.7.0**：
- UI 整体重做（新范式）
- 可观测体系（新增能力）
- 全局快捷键（新交互）
- Suno 三模式（新功能）
- Suno 额度可视化（用户能感知）
- 批量生成（前端 + 后端 + 脚本，完整闭环）
- 音乐封面模板（已 commit，但 0.6.0 已先期记录）

建议**立刻切 0.7.0**。

---

## 七、反面教材（不要这样）

- ❌ 每次 commit 都发版
- ❌ CHANGELOG 写「merge branch X to main」
- ❌ 把 git commit message 复制成 CHANGELOG
- ❌ CHANGELOG 里只有「+」和「-」符号，没人看的干货
- ❌ 发版前不跑烟测，发版后用户第一次用就崩
- ❌ 改了 breaking change 不升 MAJOR