# 运行教学示例

主示例仅依赖 Python 3.10+ 标准库；浏览器只呈现本地 GUI。无需模型或厂商 SDK。

在仓库根目录启动：

```powershell
python -m examples.local_agentlink.host --state-dir .runtime/demo --port 8765
```

打开输出 URL；软件会生成当前 session 的 Prompt。可直接复制给有本地执行工具的 Codex / Claude。端口占用可改 8766；`--port 0` 自动分配端口，使用终端打印的 URL。

也可在第二个 PowerShell 中手动走一遍（每次启动从当前 session 文件读取 ID，示例里不硬编码）：

```powershell
$calSession = (Get-Content .runtime/demo/session.json -Raw | ConvertFrom-Json).sessionId
python -m examples.local_agentlink.cli --state-dir .runtime/demo --session $calSession --live identify --name Codex
python -m examples.local_agentlink.cli --state-dir .runtime/demo --session $calSession --live inspect
python -m examples.local_agentlink.cli --state-dir .runtime/demo --session $calSession --live log --message '已检查演示工程'
python -m examples.local_agentlink.cli --state-dir .runtime/demo --session $calSession --live apply --proposal examples/proposal.json --dry-run
python -m examples.local_agentlink.cli --state-dir .runtime/demo --session $calSession --live apply --proposal examples/proposal.json
python -m examples.local_agentlink.cli --state-dir .runtime/demo --session $calSession --live inspect
python -m examples.local_agentlink.cli --state-dir .runtime/demo --session $calSession --live finish --summary '已写入并检查两段演示片段'
```

`proposal.json` 的 expectedRevision=0 适用于刚启动的 host，之后应从 inspect 获取当前版本并生成新提案。Agent 名请填实际身份；上面 Codex 只是此手动演示的示意值。接口成功输出 `{ok:true,result:...}`，错误 JSON + 非零退出码。

可在 finish 前用 apply 返回的 runId 运行 `undo --run-id <id>`；终态必须 GUI 新建会话再操作。新会话保留演示 clips / runs，但 finish 只认新会话创建的片段。cancel 保留已有结果，当前任务停止；Undo 冲突拒绝。CLI 支持显式 `--request-id UUID` 进行同进程同会话最近 256 请求缓存内的幂等重试，超时仍优先 inspect。

GUI 操作：

- 复制完整 Prompt：动画期间也复制完整文本；编辑时立即显全。新会话后编辑版会标记过期。
- 暂停 / 恢复追随：查看旧日志时不被强行拉回底部。
- 清空显示：只重置显示水位，原始日志、会话和时间线不变。
- 清理旧归档：删除受控 archive-N.jsonl 并记录清理事件，当前日志继续写。
- 取消接管 / 新会话：阻断旧写入；新会话使用新 ID / token。
- 重载结果：完成后重新读取 / 呈现 Core 当前时间线，没有自动倒计时。

Ctrl+C 正常退出 host 会释放 session 与 owner.lock。异常退出后若提示 owner.lock 已存在，先确认该状态目录没有运行中的 host，再只移除这个锁文件。不要删除整个目录当作“日志清理”。状态目录应由当前用户私有管理；教学实现没有完整平台 ACL / junction 防护。

## Qt 文本动画

`qt_prompt.py` 是独立可选示例，需在已有 PySide6 环境运行；主示例不要求安装它：

```powershell
python examples/qt_prompt.py
```

展示完整文本模型、33 ms / 60 字符显字、编辑前显全、完整复制与隐藏暂停。生产宿主通过 set_motion_enabled 传入软件 / 系统动效偏好。

