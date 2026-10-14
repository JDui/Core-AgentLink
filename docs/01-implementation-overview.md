# AgentLink 实现概览

AgentLink 是软件为本地编程 Agent 提供的任务入口与受限控制框架。软件生成当前工程的 Prompt，用户交给外部 Agent；Agent 通过 CLI / MCP 适配器调用 Core，GUI 展示真实业务变化和实时日志。

## 实现模块

| 模块 | 职责 | 本仓库入口 |
| --- | --- | --- |
| Rust Core | 通用状态机、认证、白名单、调度、适配器边界 | `crates/cal-core/src/runtime.rs` |
| Host | 独立心跳、单实例、请求领取、缓存、生命周期 | `crates/cal-cli/src/main.rs`、`crates/cal-core/src/storage.rs` |
| Rust CLI | 固定工程 / session、结构化参数、JSON 输出 | `crates/cal-cli/` |
| Python SDK | v1 文件桥客户端、超时恢复、日志投影 | `python/cal_sdk/` |
| Domain adapter | 工程状态、范围、revision、提交 / 撤回 / 完成校验 | `examples/rust_python/adapter.py` |
| Journal | JSONL、epoch / seq、分页、轮换与清理 | `crates/cal-core/src/journal.rs` |
| Qt GUI | 工作线程 IPC、Prompt、身份、日志与时间线 | `examples/rust_python/desktop.py` |
| C++ 接入 | QProcess 调用 CLI，读取同一 snapshot | `examples/cpp/` |
| Qt 组件 | 可嵌入桌面软件的分段显字、编辑前显全、复制与隐藏暂停 | `examples/qt_prompt.py` |

`examples/local_agentlink/` 保留为纯 Python / Web 教学版本；主实现与版本化协议以 Rust 和 protocol/v1 为准。该教学版本的 token、时间字段与命令格式不同，不能与 v1 混用。

## 操作闭环

1. 软件打开工程、建立独占 host 与 session，生成包含当前工程、范围、CLI、规则文件和恢复要求的 Prompt。
2. 外部 Agent 先 identify，让软件显示实际身份，再 inspect 当前权威数据。生成时摘要不能代替 inspect。
3. Agent 规划业务结果，把结构化 proposal 写到专用临时目录；使用最新 expectedRevision 做 dry-run。
4. 实际 apply 在 Core 内校验并追加结果，返回 runId；projectRevision 增加，GUI 自动刷新时间线。
5. Agent 用 inspect 核对结果；需要撤回时只撤回本任务未被人工改动的对象。日志记录操作摘要，不替代业务账本。
6. finish 检查本会话确实留下业务结果后进入终态；cancel 阻断后续提交，但保留已提交内容。

## Prompt 与接管呈现

Prompt 的完整文本模型独立于动画缓冲：600 ms 占位后每 33 ms 显示最多 60 字符；复制和开始编辑都立即显全。首次显示 / 手动重新生成才启动动画，普通日志轮询不重复播放。

接管身份、真实进度与操作状态由 Core 驱动。Qt 客户端刷新真实结果，保留用户编辑 Prompt；本例固定当前 session，替换 host 后需要关闭面板并读取新 Prompt。纯 Python Web 教学界面另展示状态边框、未知进度、隐藏暂停、系统减少动态效果、完成重载与过期 Prompt 提示。

生产软件可以增加全局接管横幅、彩虹窗口边框、低透明度代码词背景与完成后无交互重载倒计时。装饰不截获输入；自动重载必须检查未保存内容并在交互后延迟，避免打断人工工作。当前 Web 示例只实现状态边框与手动重载，不实现自动倒计时。

## 日志与清理

日志由唯一 Core writer 写入，GUI 以 epoch / seq 拉取有界投影。progress 可合并显示，写入 / 失败 / 撤回 / 完成记录保留；上翻暂停追随。清空显示推进可见水位，轮询不重放旧行；清理归档只删除受管理的旧日志文件，保留当前日志、session、工程和撤回数据。自动轮换同时限制磁盘与内存量。

## 领域适配

时间线 / 动画软件可提供通道与表达式库、timed events、淡入淡出、最终混合评估和帧预览；任务完成要求实际片段，不能只创建库定义。预览临时改变当前帧或页面后应恢复原状态；音频分析与切片路径不能证明 Agent 实际听过。

资产管理软件可提供类型 / 项目多选范围、分页 inspect、标签追加、用户移除覆盖、有效预览门槛与卡片同步。空范围不得退化为全库；扫描期间处理新发现资产时按 ID 去重，并在扫描终态后补读最后一轮。有效预览生成属于队列任务，标签提交与卡片同步分别检查结果。

这些领域接口需要软件自己的业务 adapter，本示例不执行表情渲染、音频分析、扫描或标签分类。CLI / MCP 只封装 adapter，不绕过业务校验。

## 已实现与生产补齐

Rust + Python 示例已实现 session / project / version 绑定、独立 heartbeat、白名单、有界原子文件桥、域内 scope / revision / dry-run / apply / undo / finish、取消、分页日志与清理。详见 [协议 v1](08-protocol-v1.md)。

当前工程在内存中；幂等缓存仅同进程同会话最近 256 请求有效。生产接入需补齐工程事务、持久业务 / 请求账本、系统权限与重解析路径防护、异常退出恢复、耗时 worker 与取消点、工程切换生命周期、打包后的 CLI / schema 路径与实际 GUI / 领域验收。
