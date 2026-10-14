# 本地验证记录

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

