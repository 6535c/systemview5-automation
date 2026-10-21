# SystemView5 Automation

CLI / native local API for **ELANIX SystemView 5.0 Build046**. AI agents can create blocks, connect named ports, simulate, calculate spectra and export real results without mouse automation.

面向 AI 的 SystemView 5 命令行接口：自动建模、连线、仿真、功率谱和双边 FFT。运行于 Windows 桌面，无需 Computer Use。

## 安装与运行

1. 从 [Releases](https://github.com/6535c/systemview5-automation/releases/latest) 下载并解压便携包。
2. 自行安装合法可用的 SystemView 5 Build046 和 Python 3.10+。
3. 在解压目录的 CMD 中执行；PowerShell 使用 `.\sv.cmd`。

```bat
sv.cmd config --exe "X:\YourInstallation\SysVu_32.exe"
sv.cmd doctor
sv.cmd model build "recipes\ami.json" --out "out\ami-first"
```

安装路径不限盘符。工具核对版本文件 SHA256，不会修改 SystemView 安装文件。不同二进制即使版本号相同也会拒绝；支持的 SHA256 见 [接口指南](docs/INTERFACE.md)。原版软件、许可证及第三方库不随包提供。

无需 pip 依赖。可直接从解压目录运行，也可运行 `install.ps1` 复制到当前用户程序目录；不修改 PATH、不需要管理员权限。需指定 Python 时设置 `SV5_PYTHON`。

## AI 使用入口

- [AI 快速调用指南](docs/AI_USAGE.md)
- [接口使用指南：命令、JSON 配方、Python API、故障排查](docs/INTERFACE.md)
- [构建与隐私检查](docs/BUILD_AND_PRIVACY.md)

```bat
sv.cmd model lab1 --out "out\three-models"
sv.cmd model verify "out\ami-first"
```

示例覆盖 NRZ/RZ、AMI、乘法器。AMI 同时输出单边 dBm 功率谱和黑底黄线的双边 `Cx FFT: Mag` 图。新建输出目录以避免覆盖文件。启动前关闭其他 SystemView 实例，工具不会接管未记录的会话。

配置和运行文件默认保存在当前用户的本地应用数据目录，用户生成的工程与导出文件写入指定的 `--out`。本仓库不收集遥测、不监听网络端口，不包含个人工程、仿真截图、会话文件或注册信息。使用者自己的输出文件仍可能带有本机路径和软件注册信息，应保留在本地。

这是特定版本的实验性扩展；只对示例覆盖的模块和流程做过实际软件验证。它仍需桌面进程，不是独立的无界面仿真器。

License: MIT for this adapter; SystemView remains proprietary. See [NOTICE](NOTICE).
