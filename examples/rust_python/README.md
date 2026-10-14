# Rust Core + Python 业务适配器

Rust host 维护协议、session、心跳、状态、幂等缓存、日志和清理。Python adapter 是演示软件，拥有内存中的时间线数据、revision、提交 / 撤回和完成校验。两者以有界 JSONL stdin/stdout 通信，token 不传给业务 adapter。

## 启动

需要 Rust / Cargo（依赖要求 Rust 1.85+）与 Python 3.10+。在仓库根目录构建：

```powershell
cargo build --workspace
$calPython = (Get-Command python).Source
target/debug/cal.exe serve --state-dir .runtime/rust-demo --project-id demo --python $calPython --adapter examples/rust_python/adapter.py
```

Host 输出 ready、当前 sessionId 和状态目录，不输出 token。第二个 PowerShell：

```powershell
$calSession = (Get-Content .runtime/rust-demo/session.json -Raw | ConvertFrom-Json).sessionId
target/debug/cal.exe identify --state-dir .runtime/rust-demo --project-id demo --session $calSession --name Codex
target/debug/cal.exe inspect --state-dir .runtime/rust-demo --project-id demo --session $calSession
target/debug/cal.exe apply --state-dir .runtime/rust-demo --project-id demo --session $calSession --proposal examples/rust_python/proposal.json --dry-run
target/debug/cal.exe apply --state-dir .runtime/rust-demo --project-id demo --session $calSession --proposal examples/rust_python/proposal.json
target/debug/cal.exe inspect --state-dir .runtime/rust-demo --project-id demo --session $calSession
target/debug/cal.exe finish --state-dir .runtime/rust-demo --project-id demo --session $calSession --summary '已提交并检查实际片段'
target/debug/cal.exe events --state-dir .runtime/rust-demo --project-id demo --session $calSession --after 0
```

Agent 名请填写真实身份，提案里的 expectedRevision=0 只用于初始工程；再次提交前 inspect 最新版本与轨道占用。apply 返回 runId，finish 前可 `undo --run-id <本次ID>`。所有客户端命令都是 live-only，不存在离线绕开模式。Linux / macOS 使用 target/debug/cal 对应命令。

## Python 客户端与 Qt 面板

在刚启动且还未执行上一段提交的 host 中，运行完整 SDK 工作流：

```powershell
python examples/rust_python/client.py --state-dir .runtime/rust-demo --session $calSession
```

不需要 pip 安装，示例自动定位 python/cal_sdk。其他项目可 `python -m pip install ./python`。此客户端选择演示身份 Python，实际 Agent 应通过 identify 使用自身身份。

已有 PySide6 环境中运行可选桌面面板：

```powershell
python examples/rust_python/desktop.py --state-dir .runtime/rust-demo --session $calSession --cli target/debug/cal.exe
```

面板显示 Prompt、接管身份、日志和当前时间线；操作通过 Python SDK 调用 Rust host。复制 Prompt 使用实际 CLI 绝对路径。清空显示只清 SDK 投影，清理归档由 Rust Core 执行，取消阻止后续提交。网络连接与模型推理均不由这个面板启动。

Ctrl+C 正常停止 host，回收子进程 / session / owner.lock。异常退出后，先确认无 host，再移除对应 owner.lock；不要把整个工程 / 状态目录删除作为恢复步骤。

## 当前限制

工程数据在 Python adapter 内存中，重启恢复演示初始状态；日志持久化，撤回 / 请求缓存没有持久化。Adapter 调用最多等待 5 秒，超时终止 adapter 并报告 UnknownResult；不会擅自重启或重复写入。心跳独立运行，说明 host 存活，不保证业务 adapter 正常。

本例串行分发业务操作，取消可能等待当前 adapter 调用返回（上限 5 秒），不具备任意长任务的即时取消。生产软件应把长任务变成任务 ID / 分批状态、增加提交边界取消，并持久化工程及操作账本。Qt 面板只是此教学工程的客户端，不证明任何外部软件已集成。

