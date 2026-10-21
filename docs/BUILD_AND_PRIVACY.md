# 构建、验证与发布边界

## 原生助手

仓库中的三个原生二进制只包含本项目助手：`bridge_host.exe`、`vbbridge.dll`、`SvCom.exe`。厂商程序、许可证、厂商 DLL、示例截图、用户工程和空白 `.svu` 均不分发。首次建模时，空白工程由使用者电脑上的 SystemView 自己创建。

重编译需 Visual Studio / Build Tools 的 C++ 桌面开发组件及 Windows .NET Framework 4.x。`build.cmd` 用 `vswhere` 查找安装目录，选择 x86 工具链；可从 x86 Developer Command Prompt 直接运行：

```bat
build.cmd
```

运行包已含助手，无需接收者安装编译器。Python 只用标准库。C++ 助手用静态运行库并关闭 PDB 调试信息，C# 助手不生成 PDB。MSVC 优化链接可能保留 POGO 段布局元数据；发布检查只接受该类型，拒绝 CodeView/PDB 和未知调试记录，并继续扫描全部二进制字节。`bin/win32/manifest.json` 记录助手 SHA256，运行前校验；运行副本位于用户本地目录的内容哈希子目录，避免覆盖已加载文件。

桥接主机独立校验目标 HWND/PID、进程创建时间、配置路径和 EXE SHA256 后才加载本地 DLL。它只使用目标进程的 UI 线程、本机 COM/ROT 和白名单原生事件；不监听网络端口，不写安装文件，不直接改模型内存字段。关闭时先撤销 COM 强引用。

保存完成后正常关闭所创建的会话；若所有可见文档、分析窗和提示均已消失，旧版 VB6 仍残留后台框架，则再次验证精确进程身份并清理该自有孤立进程。存在任何可见文档或未知提示时拒绝此清理。不会清理用户其他实例。

## 测试

```bat
py -3 -m unittest discover -s tests -v
sv.cmd doctor
sv.cmd model lab1 --out "out\acceptance-new"
```

离线检查覆盖助手哈希、配方格式、JSON 输出及 FFT 验证器拒绝错误数据。实际桌面验收需已安装软件，覆盖三套电路、数值关系、频谱、真实原生图和保存。测试生成文件含使用者本机信息，保留在本地，不加入发布包。

## 发布隐私检查

`tools/package_release.py` 使用显式文件白名单，逐文件扫描文本与二进制：凭据模式、个人主目录路径、可选本地私人拒绝词表（UTF-8 / UTF-16LE / GB18030），并检查 x86 PE 和调试记录类型。拒绝词表保留在发布目录之外，不会记录在公开报告中。

```bat
py -3 tools/package_release.py --deny-file "X:\Private\deny.json" --out "dist\systemview5-automation-0.1.0-windows.zip"
```

这会生成 `release-files.json`、无私人字符串的 `privacy-audit.json`、ZIP 和 SHA256 校验文件。ZIP 使用相对路径和固定时间戳，不含本机文件元数据。安装脚本只复制清单中且哈希相符的文件。

发布前还应检查 Git 暂存文件、提交作者邮箱、二进制字符串及 ZIP 解压内容。忽略规则只是辅助；新增文档、用户日志、截图和软件工程必须重新审查。GitHub 仓库所属账号会公开，这是发布平台本身的可见信息；发布内容不应包含真实姓名、私人邮箱、学号、凭据或电脑路径。

本检查是静态检测和人工复查的结合，不声称能发现任意形式编码或新增文件中的所有隐私信息。未来修改应重新运行检查。
