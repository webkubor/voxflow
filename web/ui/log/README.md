# Agent 遥测日志（按 dev 端口隔离）

多个 agent/dev server 可同目录、不同端口并行，**各自的日志在 `log/<port>/`**，互不覆盖。

- 你的 dev 端口看 `cs dev` / vite 启动输出（如 5175）。
- 你的日志在 `log/<你的端口>/`：`errors.log` / `console.log` / `interaction.log` / `api-calls.log` / `proxy-*.log` / `auth-state.json` / `snapshots/`。
- `instances.json` 列出当前在写日志的端口 / 分支 / pid，方便确认你该读哪个。
- `project-guide.json` 是项目结构体检：项目类型、API/业务/路由/配置层级、alias 和建议。

读法见 `log/<port>/README.md`。
