# Core-AgentLink（C-AL）

**本仓库面向 vibecoding 和本地 AI 软件框架设计**：为 Codex、Claude 等能够读文件、运行命令的编程大模型，提供把普通桌面软件改造成可被本地 Agent 理解、控制、验证和恢复的软件的文档与示例代码。

AgentLink 把「当前软件的上下文 → 可复制 Prompt → 外部 Agent → 受限本地 API → 软件真实变更 → 实时 Log」连起来。用户把软件生成的 Prompt 交给现有 Agent；软件保有工程和业务状态的所有权。接入模型可通过 CLI、MCP 或其他适配器，核心协议不依赖某一家模型厂商。

本仓库提供可迁移到不同桌面软件的实现框架：会话与权限、业务适配器、Prompt 文本呈现、实时日志、接管反馈与恢复。文档直接描述实现和接口，示例可以独立运行。

## 从哪里开始

| 目的 | 文档 / 示例 |
| --- | --- |
| 理解框架职责、操作闭环与实现范围 | [实现概览](docs/01-implementation-overview.md) |
| 设计 Core、CLI、GUI 和会话协议 | [技术框架](docs/02-architecture.md) |
| 组织给 Codex / Claude 的 Prompt | [Prompt 组织](docs/03-prompt-design.md)、[开发 Prompt](prompts/build-agentlink.md)、[任务模板](prompts/live-task.template.md) |
| 实现 Prompt 文本动画 | [Prompt 与接管界面](docs/04-ui-and-takeover.md)、[Qt 分段显字](examples/qt_prompt.py) |
| 实时更新、合并、清空与清理日志 | [实时日志与清理](docs/05-logs-and-cleanup.md)、[日志存储](examples/local_agentlink/journal.py) |
| 在已有软件里接入，并定义验收 | [接入与验证](docs/06-integration.md)、[Agent 指引](AGENTS.md)、[Claude 入口](CLAUDE.md) |
| 运行完整的小型本地示例 | [示例使用说明](examples/README.md) |

## 可运行示例

需要 Python 3.10+，主示例仅使用标准库。在仓库根目录运行：

```powershell
python -m examples.local_agentlink.host --state-dir .runtime/demo --port 8765
```

打开终端输出的本地页面地址，复制页面左侧 Prompt，交给能访问本机的 Agent。右侧 Log 将显示它通过 CLI 实际提交的操作；底部演示时间线会出现新片段。无本地文件 / 命令执行工具的纯网页聊天需要本地执行端。

示例包含会话 ID 与 token、心跳、原子文件请求 / 响应、命令白名单、接管身份、范围与工程版本检查、dry-run、增量追加、runId 撤回、完成条件、旧会话拒绝、实时日志与归档清理。浏览器页面通过仅绑定回环地址的 HTTP 展示 GUI；**Agent 的控制通道仍然是本地文件 IPC**。

Prompt 短暂占位后分段显字，动画期间复制完整原文；接管时显示身份与边框，业务变更即时刷新，完成时提供重载提示。日志支持追随 / 暂停追随、清空显示、清理旧归档；清空显示不会让旧历史在下次轮询时重新出现。动画可关闭，并遵循系统减少动态效果。

```powershell
python -m unittest discover -s tests -v
```

## 使用边界

这是设计文档和教学框架，真实工程接入仍需实现业务适配器、事务、平台文件权限、进程单实例与工程切换生命周期。示例工程保存在内存中，重启 host 会恢复演示数据；日志保存在指定状态目录。取消停止后续操作，已提交内容保留；撤回只移除本任务创建且未被用户改动的片段。日志不是业务撤回依据。

文档区分已实现的教学功能与生产接入需要补齐的能力；以 [实现概览](docs/01-implementation-overview.md) 与 [接入验收](docs/06-integration.md) 为准。

