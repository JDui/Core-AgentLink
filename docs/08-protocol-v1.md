# C-AL 本地协议 v1

此文档与 protocol/v1 定义 Rust 主实现的跨语言合同。早期纯 Python Web 示例不兼容本协议，使用单独状态目录。

## 会话与传输

session.json 含 version=1、sessionId、projectId、token、pid、heartbeatMs。token 仅由本地客户端读取，不进 Prompt / Log / adapter context。心跳每约 1 秒刷新，超过 6 秒视为失联，显著未来时间视为非法。

客户端显式绑定当前 projectId 与 sessionId，生成 request UUID，原子发布 requests/<session>-<request>.json。Host 领取为 .working，认证版本、工程、会话和 token，再调度。responses 中同名 JSON 原子发布。单包上限 64 KiB，UUID 规范化为小写连字符形式。受管理普通 requests / responses 超过 60 秒清理；处理中 working 文件不参加清理。

响应包含 version、id、ok、result、error。成功 error=null；失败 result=null，error={code,message}。Rust CLI 的 stdout 是 JSON envelope（没有 transport request id），serve 首先输出 ready 信息；diagnostic / adapter 诊断走 stderr。C++ 示例仅调用客户端命令，不能把 serve 多行输出当作一次响应。

## 命令

| 命令 | payload | 状态 / 所有者 |
| --- | --- | --- |
| identify | name，1–8 字符、非空白 / 控制字符 | waiting / active；Rust 绑定身份 |
| inspect | {} | 任意状态；返回 Core 状态与 domain 工程 |
| log | message≤400字符，可选整数 percent 0–100 | active；Rust 写日志 |
| events | 可选 epoch / after | 任意状态；Rust 返回日志页 |
| cleanup | {} | 任意状态；只删管理归档 |
| cancel | {} | waiting / active / cancelled；停止后续写入 |
| apply | 由 adapter 定义；示例为 expectedRevision / events / dryRun | active；域内验证和提交 |
| undo | 示例 runId | active；域内完整记录冲突检查 |
| finish | summary≤1000字符 | active；adapter 确认 finished=true 后 Core 终态 |

命令 completed 不等于 session finished；dry-run 不产生实际片段。终态允许读取日志、inspect 与 cleanup，拒绝新写入。cancel 与 undo 不相同，已提交内容保留。

inspect 返回 sessionId、projectId、status、agentName、percent、domain、journalError、transportError。domain 示例含 projectRevision、scope、clips、runIds，真正软件可以替换为自己的领域结构。

## 日志 cursor

events 页含 epoch、seq、latestSeq、reset、gap、events、error。seq 为本页最后事件，最多 8 条；继续传 epoch / after=seq，直到 seq≥latestSeq。Core 最多保留 400 条内存事件，超出窗口返回 gap，并从当前最早记录继续。单条诊断字段限制为 operation 80 字符、phase 32 字符、message 1000 字符、details 1024 字节；过大 details 以 truncated 标志代替，防止日志页突破包上限。

清空显示把 SDK visibleAfter / after 推到最新已知 latestSeq，并清投影；后续旧页的事件仍按水位过滤。不同 epoch 表示新进程的日志序列，复位水位。raw activity.jsonl 达 2 MiB 轮换，最多 2 个归档，日志文件总量约 6 MiB；业务账本不属于日志。

## 幂等、错误与超时

Host 保存同会话最近 256 请求响应，相同 request ID 与相同内容返回缓存；不同内容报 RequestIdConflict。缓存淘汰、重启后无持久保证。正式持久账本需与业务事务设计，不能承诺 exactly-once。

| error.code | 含义与动作 |
| --- | --- |
| ProtocolVersion / InvalidPacket / InvalidPayload | 修订字段或版本，禁止直接猜测重发写入 |
| StaleSession / InvalidCredential | 获取当前软件的新 Prompt，停止旧任务 |
| NotIdentified / IdentityConflict | 检查实际 Agent 身份 |
| TerminalSession | 停止写入；当前示例需新 host session |
| DomainValidation / IncompleteResult | 检查范围、revision、冲突与实际产物 |
| UnknownResult | 请求可能已提交，先 inspect；不可盲重试 |
| AdapterUnavailable / Disconnected | 检查宿主与 adapter，保留结果未知的边界 |
| IoError / HostOwnership / InvalidPath | 检查本地路径、权限、现有 host，不删除整个目录 |

CLI 默认等待 10 秒，SDK 可指定≤60 秒。请求发布前发现 stale session 可明确拒绝；发布后失联 / 会话替换 / 超时属于未知结果。Adapter 最多 5 秒返回，否则终止其进程，后续领域命令失败，不自动重启。

## Adapter 进程协议

输入一行 JSON：{id,context:{version,sessionId,projectId},command,payload}。输出一行 {id,ok,result} 或 {id,ok:false,error:{code,message}}。Host 固定 executable / script，Agent 请求不允许更改启动参数或执行 arbitrary shell。

每次只一个 outstanding 调用，返回 id 必须一致，行和包都限制 64 KiB。业务 adapter 自己验证范围、版本、数值、批大小、重叠、撤回冲突和完成条件。复杂真实 GUI 不应把工程交给新 Python 进程，而应在现有宿主工程所有者中实现 DomainAdapter 或等价桥接，保留线程语义。

