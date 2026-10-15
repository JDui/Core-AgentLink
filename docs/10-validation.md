# 本地验证记录

## 2026-10-15：终止 Agent 按钮

GPT-6 Luna（low）子代理执行验证，主代理审查实现和结果：

- Rust 离线构建通过，12 项 contracts 测试通过，包含终止信号会话隔离、确认、新写入阻断，以及 adapter 忙碌时独立发送。
- C_AL_CLI 指向新 Rust CLI 后，Python 全套 27 项测试通过；Node 语法、Python compileall、Rust 格式检查通过。
- Qt offscreen smoke：真实 Rust host / Python adapter，QTest 点击“终止 Agent”，观察 requested；独立 SDK checkpoint 确认后面板显示“Agent 已确认终止”，已提交片段保留。
- Web 接口 smoke：错误 UI 凭据返回 403；正确同源凭据接受 /stop-agent，control / ack-stop 与结果保留通过。

这是协议 / 运行与无窗口控件检查，不代表可见 GUI 动画验收。当前终止为协作命令，需 Agent 接入检查点；未注册厂商推理取消 API，也未测试或实现强杀外部 Agent 进程。

## 2026-10-14：初始框架

日期：2026-10-14。验证由 GPT-6 Luna（low）子代理执行，主代理检查实现与结果。本次在 Windows 本地环境运行，未启动云 CI。

| 项目 | 结果 | 证据范围 |
| --- | --- | --- |
| cargo build --workspace --offline | 通过 | 构建 cal-core / cal，使用本机已缓存依赖 |
| cargo test --workspace --offline | 10 项通过 | 认证 / 版本、幂等冲突、取消、完成条件、payload 校验、独占锁、日志分页 / 轮换 / 清理 / 包上限 |
| Python 单测（C_AL_CLI 已设置） | 24 项通过 | 原教学版本 17 项，adapter / SDK 投影与真实 Rust IPC 7 项 |
| 最终 Rust 文件竞态修订后的复查 | 通过 | 再构建、10 项 Rust、7 项 interop 文件内 Python 测试，包括两项真实 RustLiveTests |
| Rust 格式检查、JS 语法、Python compileall | 通过 | 静态格式与语法，不能替代 GUI 交互证明 |
| 可选 Qt v1 面板 offscreen smoke | 通过 | 构造 Panel，连接真实 Rust host / Python adapter，读取 snapshot 与原有用户片段；未显示窗口 |
| protocol/v1 四份 JSON | 可解析 | 未运行独立 JSON Schema 验证引擎 |
| Markdown 相对链接 / 无关项目字符串检查 | 通过 | 已交付目录的文件引用有效，未混入其他项目上下文 |
| C++ / Qt 示例 | 未编译 | 当前环境缺少 Qt6 C++ 开发工具链 |

在线 Cargo 获取 index 曾遇到 schannel TLS 凭据错误；离线缓存可用，随后完成构建与测试。Cargo 提示无法规范化用户目录的警告，未导致本轮构建或测试失败。

已配置 Windows / Ubuntu 的 Rust 构建与 Python 互操作 CI，但本地成功不代表远端 CI 已运行。未验证可见 Qt 界面动画、长期负载、生产工程事务、平台 ACL / junction 防护、实际领域渲染 / 音频结果。工程和请求缓存仍有 [实现路线](07-implementation-roadmap.md) 中列出的教学边界。

