# “终止 Agent”按钮与控制通道

按钮向当前会话的 Agent 发送可机器读取的 terminate 命令。它与 cancel 不同：cancel 只停止软件侧后续操作，stop-agent 还产生 Agent 必须检查的终止信号。两者均保留已提交工程内容；撤回仍需自己的业务规则。

## 状态与用户反馈

1. 点击“终止 Agent”，通过当前 session / project / token 发布请求。
2. Core 写入 agent-control.json，status=requested，后续新写入被拒绝；GUI 显示“终止命令已发送，等待 Agent 确认”。重复发送保留首次请求和原因。
3. Agent 的检查点读取 terminate，停止新操作、释放任务资源，发送 ack-stop，再结束当前任务。
4. GUI 看到 acknowledged 后显示“Agent 已确认终止”。这个确认表示 Agent 适配代码响应了协议，不代表 IDE / 模型宿主进程已被杀死。

Qt 面板用独立工作线程发送命令；Rust 控制队列由心跳线程收取，不受普通业务 adapter 的串行等待影响。普通 inspect 可能还在等待业务返回，按钮仍能显示独立发送结果。若发送超时显示状态未知，应查询 control，不谎称未发送或已终止。

## Agent 侧 Python 示例

```python
from cal_sdk import AgentLink, AgentLinkError

client = AgentLink(state_dir, current_session_id, project_id)
try:
    for item in work_items:
        client.checkpoint()  # 收到 terminate：ack-stop，再抛 AgentTerminationRequested
        # 执行有界任务；耗时循环内也放检查点
        process_one(item)
except AgentLinkError as error:
    if error.code != "AgentTerminationRequested":
        raise
    release_task_resources()
    # 返回 / 退出本次任务；不发送成功 finish，不继续写入
```

清理任务资源应使用 finally 等宿主生命周期机制；checkpoint 只能协作退出调用方代码，不能从另一个线程强制打断任意正在运行的函数。SDK 在新写入前也检查信号并拒绝继续工作，调用方用 checkpoint 完成确认。

GUI 的定期 inspect / control 不应调用 checkpoint 或 ack-stop。否则会产生“Agent 已确认”的假象。CLI Agent 每步前及长任务期间执行 `cal control --state-dir ... --project-id ... --session ...`；result 非 null 时停止工作，执行相同参数的 ack-stop，再结束对话任务。

## 协议和权限

- 独立目录 control-requests / control-responses，使用同样的 64 KiB 限制、原子发布和文件名 / request ID 校验。
- 每条请求绑定 version、projectId、sessionId 与 token；错误凭据、旧会话或替换 session 被拒绝。
- agent-control.json 不含 token，包含 requestId、reason、requestedAtMs 和 acknowledgedAtMs。
- 原有状态、业务记录、撤回账本和已提交结果不因终止而删除。正在提交的操作可能已经成功，终止不能伪造回滚。
- 新 host 会话重置终止信号；旧控制队列请求仍不能命中新会话。日志分别记录 requested 和 acknowledged。

## 能力边界

外部编程 Agent 必须接入检查点或控制通道，才能响应这条命令。未接入的模型可能继续生成文本，但软件不再接受本会话新写入。若需要终止某个厂商 Agent 的真实推理 / 运行任务，应由宿主适配它提供的取消 API，并确认目标任务归属；当前示例没有注册厂商取消 API，也不按进程名结束其他程序。

早期纯 Python Web 教学示例也提供按钮及 control / ack-stop 协作合同，但沿用自己的教学传输格式，不与 Rust v1 共用目录。
