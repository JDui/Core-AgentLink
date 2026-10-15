# Core-AgentLink（C-AL）

**本仓库面向 vibecoding 和本地 AI 软件框架设计**：为 Codex、Claude 等能够读文件、运行命令的编程大模型，提供把普通桌面软件改造成可被本地 Agent 理解、控制、验证和恢复的软件的文档与示例代码。

AgentLink 把「当前软件的上下文 → 可复制 Prompt → 外部 Agent → 受限本地 API → 软件真实变更 → 实时 Log」连起来。用户把软件生成的 Prompt 交给现有 Agent；软件保有工程和业务状态的所有权。接入模型可通过 CLI、MCP 或其他适配器，核心协议不依赖某一家模型厂商。

本仓库采用 **Rust 主核心 + Python SDK / 业务示例 + C++ 可选适配层**。Rust 管理会话、协议、调度与日志；宿主软件的业务适配器负责工程校验、提交和撤回。文档直接描述实现和接口，示例可以独立运行。

## 从哪里开始

| 目的 | 文档 / 示例 |
| --- | --- |
| 理解框架职责、操作闭环与实现范围 | [实现概览](docs/01-implementation-overview.md) |
| 设计 Core、CLI、GUI 和会话协议 | [技术框架](docs/02-architecture.md) |
| 理解 Rust / Python / C++ 的分工与迭代边界 | [实现路线](docs/07-implementation-roadmap.md) |
| 实现跨语言客户端和业务适配器 | [协议 v1](docs/08-protocol-v1.md)、[协议定义](protocol/v1/README.md)、[跨语言接入](docs/09-polyglot-integration.md) |
| 组织给 Codex / Claude 的 Prompt | [Prompt 组织](docs/03-prompt-design.md)、[开发 Prompt](prompts/build-agentlink.md)、[任务模板](prompts/live-task.template.md) |
| 实现 Prompt 文本动画 | [Prompt 与接管界面](docs/04-ui-and-takeover.md)、[Qt 分段显字](examples/qt_prompt.py) |
| 实时更新、合并、清空与清理日志 | [实时日志与清理](docs/05-logs-and-cleanup.md)、[Rust 日志存储](crates/cal-core/src/journal.rs) |
| 在已有软件里接入，并定义验收 | [接入与验证](docs/06-integration.md)、[Agent 指引](AGENTS.md)、[Claude 入口](CLAUDE.md) |
| 运行 Rust 主核心与 Python 工程 | [混合示例](examples/rust_python/README.md) |
| 体验无需 Rust 的教学界面 | [Python / Web 示例](examples/README.md) |

## 可运行示例

推荐运行 Rust Core + Python 业务适配器，需要 Rust / Cargo 与 Python 3.10+。在仓库根目录运行：

```powershell
cargo build --workspace
$calPython = (Get-Command python).Source
target/debug/cal.exe serve --state-dir .runtime/rust-demo --project-id demo --python $calPython --adapter examples/rust_python/adapter.py
```

使用 host 输出的当前 session ID 调用 Rust CLI 或 Python SDK。[完整命令与可选 Qt 面板](examples/rust_python/README.md) 展示 identify → inspect → dry-run → apply → inspect → finish，以及取消、撤回、日志与清理。[C++ / Qt 示例](examples/cpp/README.md) 使用结构化进程参数接入同一 CLI。

Rust 主实现包含协议版本 / 工程 / 会话绑定、token、独立心跳、原子文件请求 / 响应、命令白名单、接管状态、有界日志分页与归档清理。Python 工程适配器提供范围 / revision 检查、dry-run、增量追加、runId 撤回与真实完成条件。所有客户端控制通道均为本地文件 IPC；不依赖模型厂商 SDK。

可选 Qt 面板显示当前状态、Prompt、实时日志与业务结果，IPC 在工作线程执行。Prompt 分段显字并完整复制；清空显示与删除归档分别管理。Qt 动效偏好由宿主传入。

Qt 与 Web 示例均提供 **“终止 Agent”** 按钮：向当前会话发送 terminate 命令，阻止后续写入，保留已提交结果，并区分“等待确认”和“Agent 已确认”。Rust 使用独立控制通道，普通业务请求忙碌时也能发送。Agent 通过 SDK checkpoint 或 CLI control / ack-stop 协作退出；这不会强杀外部编程工具进程。[终止控制接入](docs/11-agent-termination.md)

不需要 Rust 的入门体验可使用 [纯 Python 教学示例](examples/README.md)：

```powershell
python -m examples.local_agentlink.host --state-dir .runtime/python-demo --port 0
```

该示例保留浏览器双栏界面、接管边框、系统减少动态效果和重载提示；使用早期教学协议，不与 Rust v1 共用状态目录。它不是另一套正式核心。

## 验证

```powershell
cargo test --workspace
$env:C_AL_CLI = (Resolve-Path target/debug/cal.exe).Path
python -m unittest discover -s tests -v
```

本轮本地验证与未验证范围见 [验证记录](docs/10-validation.md)。远端 CI 尚未运行。

## 使用边界

这是可执行参考框架，尚未作为生产级 SDK 发布。业务示例保存在内存中，重启恢复演示数据；取消保留已提交内容，撤回拒绝用户编辑冲突。幂等缓存只在当前进程内有效。生产接入仍需工程事务、持久业务 / 请求账本、平台权限、工程切换与长任务取消；日志不是业务撤回依据。

文档区分已实现的教学功能与生产接入需要补齐的能力；以 [实现概览](docs/01-implementation-overview.md) 与 [接入验收](docs/06-integration.md) 为准。

