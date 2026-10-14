# C++ / Qt 接入示例

本例用 Qt6 Core 的 QProcess 调用 Rust CLI，读取当前工程 snapshot。参数逐个传入，不使用 shell 拼接，也不维护另一份协议 / 会话核心。示例固定 projectId=demo。

需要 CMake 3.21+、C++17 编译器、Qt6 Core 的开发环境；在仓库根目录执行：

```powershell
cmake -S examples/cpp -B build/cpp -DCMAKE_PREFIX_PATH='你的Qt安装目录'
cmake --build build/cpp --config Release
```

先按 [混合示例](../rust_python/README.md) 启动 Rust host，使用当前 session ID：

```powershell
build/cpp/Release/cal_qt_client.exe '仓库绝对路径/target/debug/cal.exe' '.runtime/rust-demo' '<当前session-id>'
```

单配置构建的可执行文件通常在 build/cpp/，以实际生成位置为准。生产 GUI 不在主线程 waitForFinished，应接入 QProcess finished / errorOccurred 信号，给状态与超时明确反馈。当前代码是命令行示例；没有安装 Qt 开发工具链时，只能进行源码检查，不能称编译通过。

需要进程内接入时，可由宿主实现 Rust DomainAdapter 或后续增加 C ABI；当前未交付 C ABI / DLL 接口。通过 CLI 接入不会直接取得 GUI 主线程的工程写入权限，业务修改仍由软件适配器完成。

