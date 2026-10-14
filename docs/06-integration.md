# 接入已有软件与验收

1. 找到工程所有者、保存流程、GUI 刷新路径与现有业务 API；先实现 inspect snapshot，不增加模型调用依赖。
2. 抽出业务 adapter：校验 proposal、事务提交、结果 ID / revision、按任务撤回、完成验证。GUI 按钮与 Agent API 共用。
3. 在软件生命周期内创建 bridge。Qt 在工程打开 / 切换时绑定与轮换；Tauri 在 Core 内维护 session，前端 invoke 获取 snapshot。CLI 使用显式 session / token 和原子文件请求。
4. 增加结构化 CLI 输出、错误类别、size / batch / scope 限制、取消点和幂等账本。长任务 worker 不阻塞心跳，事务前复查 session / revision。
5. 构建 Prompt 模型：真实路径、当前范围、领域 Skill / schema、读取 / 写入 / 恢复 / 验证标准。缺 CLI / Skill 时阻止误导性复制。
6. 连接身份、接管、日志与业务 revision 到 GUI；实现 Prompt 显字、完整复制、减弱动效，保护手工编辑 Prompt。
7. 接入日志投影、清空显示 cursor、归档轮换与受限清理；分离业务账本，记录清理失败。
8. 按下表验收；软件打包时包含 CLI、相关规则 / schema、模型必要依赖，验证打包后的路径与 live 连接。

| 验收层 | 必须证明 | 不能推导 |
| --- | --- | --- |
| 协议 | stale session / token / request 拒绝，scope 和 revision 校验，取消阻止后续提交 | 真正 GUI 画面正确 |
| 业务 | dry-run 不写，apply 有结果，undo 冲突保留用户改动，finish 检查真实产物 | 创作质量达标 |
| IPC 集成 | 独立 CLI 子进程对正在运行 host 控制，heartbeat / timeout / 会话轮换正确 | 原软件 / 真实工程已接入 |
| 日志 | bounded disk / memory，归档清理与 clear cursor，rotation / gap / IO error 反馈 | 长时间高负载与所有文件系统可靠 |
| 呈现 | 实际 UI 中复制完整 Prompt、修改保留、滚动、隐藏 / reduced-motion、身份与终态 | 单元测试或截图静态检查等于全部 GUI 交互通过 |
| 领域证据 | 检查实际预览、音频或其他领域产物 | 数值分析 / 提取路径等于看过或听过 |

本仓库的自动测试覆盖教学 Core、Journal 与真实 CLI / host 文件桥；浏览器与可选 Qt 检查范围另行报告。没有运行实际接入软件时，不以源码阅读代替运行证明。主示例可以独立运行。

Rust 主实现运行 cargo build / test --workspace，再将 C_AL_CLI 指向生成的 cal 可执行文件，运行 Python 单测以启用真实跨语言 IPC 检查。未设置该变量时，互操作测试明确 skip，不能报告互操作通过。具体命令见 [混合示例](../examples/rust_python/README.md)。

