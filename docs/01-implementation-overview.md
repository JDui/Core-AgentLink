# AgentLink 实现概览

AgentLink 是软件为本地编程 Agent 提供的任务入口与受限控制框架。软件生成当前工程的 Prompt，用户交给外部 Agent；Agent 通过 CLI / MCP 适配器调用 Core，GUI 展示真实业务变化和实时日志。

## 实现模块

| 模块 | 职责 | 本仓库入口 |
| --- | --- | --- |
| Core | 工程状态、范围、revision、业务校验、提交 / 撤回 / 完成条件 | `examples/local_agentlink/core.py` |
| Host | 当前 session、token、心跳、单实例、原子请求收取、响应缓存、生命周期 | `examples/local_agentlink/host.py` |
| CLI | 固定 session、live 校验、结构化参数、JSON 响应、超时恢复提示 | `examples/local_agentlink/cli.py`、`examples/agentlink_cli.py` |
| Transport | 有界 JSON 文件、同目录原子发布、heartbeat 检查、请求 / 响应路径 | `examples/local_agentlink/transport.py` |
| Journal | JSONL、epoch / seq、内存窗口、归档轮换、受限清理、IO 错误反馈 | `examples/local_agentlink/journal.py` |
| Web GUI | Prompt 显字 / 编辑 / 复制、接管身份、真实进度、Log 与时间线 | `examples/local_agentlink/web/` |
| Qt 组件 | 可嵌入桌面软件的分段显字、编辑前显全、复制与隐藏暂停 | `examples/qt_prompt.py` |

## 操作闭环

1. 软件打开工程、建立独占 host 与 session，生成包含当前工程、范围、CLI、规则文件和恢复要求的 Prompt。
2. 外部 Agent 先 identify，让软件显示实际身份，再 inspect 当前权威数据。生成时摘要不能代替 inspect。
3. Agent 规划业务结果，把结构化 proposal 写到专用临时目录；使用最新 expectedRevision 做 dry-run。
4. 实际 apply 在 Core 内校验并追加结果，返回 runId；projectRevision 增加，GUI 自动刷新时间线。
5. Agent 用 inspect 核对结果；需要撤回时只撤回本任务未被人工改动的对象。日志记录操作摘要，不替代业务账本。
6. finish 检查本会话确实留下业务结果后进入终态；cancel 阻断后续提交，但保留已提交内容。

## Prompt 与接管呈现

Prompt 的完整文本模型独立于动画缓冲：600 ms 占位后每 33 ms 显示最多 60 字符；复制和开始编辑都立即显全。首次显示 / 手动重新生成才启动动画，普通日志轮询不重复播放。

接管身份、边框和真实进度由 Core 状态驱动。未知百分比使用不定进度；完成、取消与断开停止工作动效，隐藏暂停，软件动效开关与系统减少动态效果生效。提交刷新真实业务对象，完成后提供重载结果按钮。手工 Prompt 编辑保留；会话变化后编辑版标记过期并禁用复制。

生产软件可以增加全局接管横幅、彩虹窗口边框、低透明度代码词背景与完成后无交互重载倒计时。装饰不截获输入；自动重载必须检查未保存内容并在交互后延迟，避免打断人工工作。当前 Web 示例只实现状态边框与手动重载，不实现自动倒计时。

## 日志与清理

日志由唯一 Core writer 写入，GUI 以 epoch / seq 拉取有界投影。progress 可合并显示，写入 / 失败 / 撤回 / 完成记录保留；上翻暂停追随。清空显示推进可见水位，轮询不重放旧行；清理归档只删除受管理的旧日志文件，保留当前日志、session、工程和撤回数据。自动轮换同时限制磁盘与内存量。

## 领域适配

时间线 / 动画软件可提供通道与表达式库、timed events、淡入淡出、最终混合评估和帧预览；任务完成要求实际片段，不能只创建库定义。预览临时改变当前帧或页面后应恢复原状态；音频分析与切片路径不能证明 Agent 实际听过。

资产管理软件可提供类型 / 项目多选范围、分页 inspect、标签追加、用户移除覆盖、有效预览门槛与卡片同步。空范围不得退化为全库；扫描期间处理新发现资产时按 ID 去重，并在扫描终态后补读最后一轮。有效预览生成属于队列任务，标签提交与卡片同步分别检查结果。

这些领域接口需要软件自己的业务 adapter，本示例不执行表情渲染、音频分析、扫描或标签分类。CLI / MCP 只封装 adapter，不绕过业务校验。

## 已实现与生产补齐

示例已实现 session / token / heartbeat、旧 session 拒绝、请求大小限制、白名单、scope / revision 校验、dry-run、追加 / 撤回、完成条件、取消、实时有界日志、清空显示、归档清理和过期 IPC 清理。

当前工程在内存中；幂等缓存仅同进程同会话最近 256 请求有效。生产接入需补齐工程事务、持久业务 / 请求账本、系统权限与重解析路径防护、异常退出恢复、耗时 worker 与取消点、工程切换生命周期、打包后的 CLI / schema 路径与实际 GUI / 领域验收。
