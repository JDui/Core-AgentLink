# 给 Codex / Claude 的开发任务 Prompt

请在当前软件中实现 AgentLink。目标是面向 vibecoding 和本地 AI 软件框架，让外部编程 Agent 使用软件当前工程生成的 Prompt，通过受限本地接口操作真实业务，并在 GUI 实时反馈。

先阅读仓库现有指引、Core-AgentLink 的 README 与 docs/01–06，再检查软件的工程状态、保存、撤回和刷新路径。参考既有栈，不更换 UI 框架，不让 GUI 自行启动外部 Agent。

实现要求：

1. Core 持有业务校验与写入；CLI / MCP 包装现有 API；GUI 呈现 snapshot。列清允许编辑的模块和受保护依赖，保留现有工作。
2. session ID / token / heartbeat，所有 live 请求显式绑定 session；工程切换 / 新会话使旧请求失效。权限、范围、revision 和批次校验在 Core 强制执行。
3. identify / inspect / log / validate 或 dry-run / apply / undo / finish / cancel；把领域操作映射到业务 adapter，不生造通用接口替代实际保存流程。
4. Prompt 显示真实工程 / 范围、CLI / Skill / schema 路径、数据依据、临时目录、完成标准、写入和恢复规则。文本分段显字，复制完整文本；手工编辑不被刷新覆盖，过期明确提示。
5. 接管后显示实际 Agent 名与工作状态，刷新真实结果；完成验证后提供重载。取消后保留已提交内容，撤回拒绝用户后续编辑冲突。未知进度不伪造百分比。
6. 日志实时增量、合并稠密 progress / evaluate、限制 UI 与磁盘量。增加清空显示水位、受限归档清理与过期 IPC 清理，绝不清除业务 / undo 账本。
7. 装饰动画不影响输入，隐藏暂停，支持软件开关和系统减少动态效果；断开 / 取消 / 完成停止工作动画。
8. 先审查最终 diff，再执行协议、业务与 live CLI 测试；实际操作 GUI 核查 Prompt 复制、日志滚动 / 清理、身份 / 动效 / 结果刷新。报告具体通过项和未验证项，不以构建等同视觉证明。

结束时交付变更文件、操作入口、运行示例和验证证据。若写请求超时，先 inspect 判断实际结果，不盲重试。

