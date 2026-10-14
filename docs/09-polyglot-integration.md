# Rust / Python / C++ 接入边界

## Rust 主核心

cal-core 提供 DomainAdapter trait、Runtime、client::request、Journal 和带版本的协议类型。Rust 宿主可以直接实现 DomainAdapter，避免启动 Python。当前 cal serve 演示 ProcessAdapter；将真实宿主的保存和撤回放在 trait 实现内，不能把通用 runtime 当领域数据库。

心跳独立线程；业务提交串行。真正软件如需多任务并发，必须设计工程级调度、版本冲突、取消点及持久操作记录，不能通过简单增加线程绕过 GUI / 工程所有权。

## Python SDK / 业务适配

从 python/cal_sdk 导入 AgentLink(state_dir,session_id,project_id)。call 返回业务结果，AgentLinkError.code 可判别恢复路径。LogProjection 管理显示水位与 progress 合并；clear 不写 host 文件。SDK 不依赖模型 API，不写当前工程。

examples/rust_python/adapter.py 是应用的时间线示例：inspect 提供权威项目版本，apply dry-run 不写，实际提交记录 runId / sessionId，undo 冲突拒绝，finish 检查真实片段。Qt 客户端通过独立 QThread worker 执行 SDK 调用，UI 主线程只呈现；未保存工程和渲染等业务需要宿主自己补齐。

## C++ 接入

examples/cpp 使用 QProcess 的 program / arguments 调用同一个 Rust CLI，并检查 JSON / 退出码。它避免复制协议解析与认证核心；路径含空格也不会被拆成 shell 命令。生产 GUI 使用异步信号，不在主线程等待。

进程内 FFI 与进程间 CLI 是不同交付。当前未实现 C ABI、DLL、Rust/C++ 对象传递、回调或零拷贝。选择 FFI 前定义线程、生命周期、内存释放、版本和 panic / exception 边界；不要向业务调用方暴露 Rust 私有布局。

## 模型接入

Codex / Claude 等执行同样的运行 Prompt 与 CLI；MCP 适配器可以进一步包装这组命令，但当前仓库未提供运行中的 MCP server。包装时保留 project / session / version / 取消与未知结果语义，不能让模型绕过 adapter。Prompt 自动生成无需内嵌模型推理；模型调用层属于宿主或用户现有 Agent 环境。

