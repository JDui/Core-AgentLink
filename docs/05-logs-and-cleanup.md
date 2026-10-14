# 实时 Log 与额外清理机制

## 三层数据

业务操作记录 / 撤回账本、原始日志、GUI 投影分别管理。原始 JSONL 是诊断流；业务 runId / before-after 应由工程或事务账本保存，不能因清理 Log 丧失撤回能力。v1 事件含 epoch、seq、timeMs、sessionId、operation、phase、message、details、percent；不保存 token。

采用单一 Core writer；每个事件完整序列化成一行再写。限制事件大小 / 文本长度，磁盘日志有硬上限；IO 失败反馈 GUI，不能假装已保存。多个 CLI 并发提交经 Core 排队，禁止各自直接 append 同一日志文件。

## 实时读取

直接 tail JSONL 可采用 byte offset + 不完整行缓冲，每块设置上限。Rust v1 使用独立 events 命令：每页最多 8 条，seq 是本页末游标，latestSeq 是当前全部事件水位。Python LogProjection 在 clear 时推进到 latestSeq，避免未读历史或旧 in-flight 页回放。epoch 变化复位，gap 表示 cursor 超出保留窗口；Qt 客户端应明确提示该缺口。

Qt v1 面板每 500 ms 尝试读取 inspect / events，用 busy 标志避免重叠，IPC 在工作线程执行。仅开启追随且原先接近底部时滚动。纯 Python Web 教学界面采用前台 333 ms / 隐藏 1000 ms，并展示上翻暂停与恢复按钮。生产轮询还应在隐藏时降频。

高频 progress / evaluate 仅在显示层按 session + operation + phase 合并，最终最近信息保留；写入、失败、撤回和完成不合并。GUI 最多 400 行；每轮新增动画也应限制数量。当前示例只对 progress 做显示合并；领域 evaluate 由业务适配器补充。

## 三种清理的不同语义

| 操作 | 行为 | 不影响 |
| --- | --- | --- |
| 清空显示 | 将 visibleAfter 设为已接收最大 seq，清 UI 投影；请求中的旧事件再到达也按水位过滤 | session、状态、raw log、业务结果与 undo |
| 清理旧归档 | Core 在 writer lock 内只删除自主管理的 archive-数字.jsonl；追加清理审计事件 | 当前 activity.jsonl、session、请求、业务文件 |
| 自动保留限制 | 当前文件 2 MiB，最多 2 个归档；滚动时删除最老归档，进程间依独占 host 管理 | 当前工作和业务记录 |

默认硬盘保留上限为约 6 MiB（当前 + 两份归档），示例单事件不得大于一个文件的上限。常量可配置给 Journal；归档编号每次从现有文件最大值继续，重启不会覆盖同名历史。清理归档无需关闭 Agent，仍由唯一 writer 串行处理。

不能用“清空显示”把 seq / session / percent / runIds 清零；不能把整个状态目录递归删除当日志清理。清理不读取或删除任意用户路径、符号链接 / 重解析路径。生产 Windows 使用用户私有目录并按平台 API 防 junction 穿越；教学示例拒绝直接 symlink 并限定文件名，不能代替完整 hostile-filesystem 防御。

## 过期 IPC 清理与其他生产扩展

Host 定期清理 requests / responses 中自身规范 UUID 文件名且超过 60 秒的普通文件；请求更早有 10 秒 CLI 超时。旧会话请求即时拒绝，孤立响应过期删除；处理中请求先领取，不参与普通清理。示例只处理短任务，生产长任务需 pending / executing 标记，清理器不得删除活动请求 / 响应或幂等账本。

生产可增加“保留 7 天 / 总空间限额 / 导出后清理”，但必须明确 UI 显示水位、raw retention、业务审计 retention 的差异。导出只包含脱敏日志，并提供可见失败反馈。日志断行 / 文件轮换 / 写失败 / 重启 epoch / 用户上翻 / clear 与 in-flight poll 应各有测试。

