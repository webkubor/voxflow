# 通知发不出去，按这个顺序查

> 2026-09-13 建。那天为了发一条版本日志绕了十几轮，**绝大部分时间花在错误的方向上** ——
> 而每一步本来都有更快的判断依据。这份清单就是那次的复盘。

---

## 先记三条通则

**① 空结果不等于「没有」。** 空结果有两种可能：真的没有，或者**你没取对字段**。
这两种在代码里长得一模一样。区分它们唯一的办法是**看原始返回**，不是看解析后的长度。

> 那天 `+chat-list` 返回的群在 `data.chats`，我按 `data.items` 取 → 拿到空 →
> 直接下了「机器人没被加进任何群」的业务结论，还让用户去飞书做一件根本不用做的事。

**② 多身份的工具，要分身份试。** lark-cli 有 `bot` 和 `user` 两种身份，
**看得见的东西完全不同**：bot 只在被拉进的群里，user 在自己所有的群里。
一个身份返回空，换另一个再看。

**③ 报错要归属到正确的账号。** 多 profile 环境下，A 的报错很容易被记到 B 头上。
每条报错都确认一遍它来自哪个 profile。

---

## 排查顺序

### 第 1 步：程序找得到吗（最容易被跳过）

```bash
.venv/bin/python -c "from core import notify; print(notify.find_lark_cli() or '❌ 找不到')"
```

**为什么排第一**：`lark-cli` 装在 mise 管理的 node 里
（`~/.local/share/mise/installs/node/<ver>/bin/`），而**非交互式 shell
（后端服务、cron、subprocess）没有 mise 注入的 PATH**。
`shutil.which` 找不到 → 静默回落 webhook → 看起来像「webhook 坏了」，
实际是两条通道都不通，其中一条从来没跑过。

这类故障的信号：**某条代码路径从来没出现在日志里**。

### 第 2 步：授权还有效吗

```bash
lark-cli auth status --profile <名字>
```

看两件事：
- `identities.bot` / `identities.user` 各自的 `status`
- **`refreshExpiresAt`** —— 过期后通道会**静默失效**，症状是发不出去但不报错

### 第 3 步：这个身份看得见目标群吗

```bash
# 一定要看原始输出，不要先解析
lark-cli im +chat-list --profile <名字> --as user --page-all | head -40
```

群在 **`data.chats`**（不是 `items`）。bot 身份为空是正常的，换 `--as user` 再看。

### 第 4 步：通道本身通不通

```bash
.venv/bin/python -c "
from core import notify
acc = notify.account('changelog')
print('通道:', 'lark-cli' if acc.get('profile') and acc.get('chat_id') else 'webhook')
ok, err = notify._post(acc['webhook'], notify._card('自检','blue',{'x':'y'},None)) if acc.get('webhook') else (None,'无 webhook')
print('webhook:', ok, err)
"
```

`notify()` **设计上吞掉所有异常**（旁路不该影响主流程），所以要拿错误必须调底层。

常见错误码：

| 错误 | 含义 | 怎么办 |
|---|---|---|
| `19007 Bot Not Enabled` | 群里的自定义机器人被**停用** | 群设置 → 群机器人 → 重新启用 |
| `Bot/User can NOT be out of the chat` | 这个身份不在目标群里 | 把 bot 拉进群，或改用 user 身份 |
| `missing required scope` | 该 profile 缺权限 | **先确认是哪个 profile 报的** |

---

## 凭据从哪来

**一律查 `cs kyvault`，不要问人、更不要让人把密钥贴进对话。**

```bash
cs kyvault list | grep -i feishu          # 看有哪些（只出元信息）
cs kyvault run --env T=secret://feishu/xxx -- <命令>   # 首选：注入子进程，不落盘
```

飞书相关的键已经很全：各群 webhook、各应用的 app-id / app-secret。
`lark-cli` 是例外 —— 它的授权存在自己的 auth 里，**不需要 kyvault**。

---

## 配置在哪

`~/.voxflow/configs/notify.json`，每个账号两条通道二选一：

```jsonc
{
  "accounts": {
    "changelog": {
      "profile": "hym-company",                       // ← 配了 profile + chat_id
      "chat_id": "oc_xxxxxxxx",                       //   就走 lark-cli
      "webhook": "https://open.feishu.cn/...",        // ← 否则走 webhook
      "mute": []                                      //   两个都没有 = 没开通知
    }
  }
}
```

**两条通道有一条通就够**，不用都修好。
