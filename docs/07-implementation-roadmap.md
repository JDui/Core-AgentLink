# 实现路线与仓库职责

主实现使用 Rust，Python 提供轻量 SDK、工程适配与易读示例，C++ 通过 CLI 接入。模型只需要结构化调用能力，不承担协议或日志管理。

| 目录 | 维护职责 |
| --- | --- |
| crates/cal-core | 唯一 v1 通用 Core：会话、白名单、原子存储、调度、日志、客户端 |
| crates/cal-cli | serve 与 live 客户端命令，复用 Core 类型和传输 |
| protocol/v1 | 语言无关字段定义、JSON Schema、变更规则 |
| python/cal_sdk | 文件桥客户端与日志投影，不写业务数据 |
| examples/rust_python | Python timeline adapter、SDK 工作流、可选 Qt 客户端 |
| examples/cpp | C++ / Qt CLI 客户端，不维护另一份 Core |
| examples/local_agentlink | 入门 Web 教学实现，使用独立早期协议 |
| prompts / docs | 面向编程 Agent 的开发 / 运行合同、接入和验收 |

## 当前已落地

Rust workspace 可构建库与 cal CLI；Python 工程由 Rust host 启动固定 adapter 子进程。真实 CLI 和 SDK 使用同一 v1 session，业务修改返回 runId / revision。日志分页、clear 水位、轮换、cleanup 与命令终态分别处理。可选 Qt 面板工作线程执行 IPC，C++ 示例结构化调用 CLI。

## 下一阶段必须补齐的生产能力

- 把域内事务、runId / before-after 与幂等请求账本持久化；当前内存缓存仅当前进程有效。
- 将长任务改为 start / status / cancel 的任务 ID 机制，在提交边界检查 cancellation / revision；当前串行 adapter 最多等待 5 秒。
- 工程切换 / 新会话在宿主生命周期内轮换，保留工程；当前 Rust 教学 host 重启会重置演示数据。
- Windows ACL / junction 防护与其他平台私有目录权限、异常退出恢复、旧 working 请求审计。
- 平台安装包、SDK 版本发布、可见 GUI 与实际领域产物验收。

本轮不添加模型供应商依赖、C ABI 或 DLL；C++ 可使用成熟的进程边界接入。未来进程内 API 需要明确线程、生命周期、缓冲区所有权和错误 ABI，再决定是否加入。

