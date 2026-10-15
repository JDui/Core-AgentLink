# C-AL 协议 v1 的语言无关定义

字段与命令语义见 [协议文档](../../docs/08-protocol-v1.md)。Schema 用于生成文档、编辑器辅助与跨语言一致性检查；运行时仍由 Rust serde 类型和业务适配器验证，不能只依赖 JSON Schema 宣称安全。

| 文件 | 内容 |
| --- | --- |
| [session.schema.json](session.schema.json) | 本地 session 文件，包含私有 token |
| [request.schema.json](request.schema.json) | 客户端到 Core 的请求 envelope |
| [response.schema.json](response.schema.json) | Core 到客户端的响应 envelope |
| [timeline-proposal.schema.json](timeline-proposal.schema.json) | 教学时间线 adapter 的提案 |
| [agent-control.schema.json](agent-control.schema.json) | 独立 Agent 终止命令与确认状态 |

UUID 用小写连字符规范形式；token 不出现在 Prompt、Log 和 adapter context。schema 不代表磁盘 / batch / runtime 状态校验：64 KiB 包限制、主机心跳、白名单状态机、轨道重叠、版本冲突、撤回和完成条件都在运行时强制处理。

同 v1 仅做不改变既有语义的兼容修改；新增必需字段、改变命令含义或 wire format 时提升协议版本，显式拒绝旧客户端。当前没有自动迁移早期 Python 教学协议。Rust 类型、SDK、schema、示例和文档必须在同一改动中更新。

