# AI 快速调用指南

项目：SystemView5 Automation。目标：ELANIX SystemView 5.0 Build046；不是 SEGGER SystemView，也不是现代 Keysight SystemVue。

## 首次使用

1. 下载 GitHub Release 便携 ZIP，解压到可写目录。也可克隆公开仓库。
2. 用户需已有合法可用的目标软件及 Python 3.10+；原版不在此包中。
3. 在正常 Windows 桌面终端运行，不使用隔离服务会话。无需管理员权限。
4. 确认其他 SystemView 实例已关闭，再配置并检查：

```bat
sv.cmd config --exe "X:\YourInstallation\SysVu_32.exe"
sv.cmd doctor
sv.cmd model build "recipes\ami.json" --out "out\ami-run-001"
```

`doctor` 失败时先解决实际原因。不要绕过二进制哈希校验。程序路径可以任意配置，受支持二进制 SHA256 固定为：

```text
82f1a0f823450dcf9439370c3e7c601e99da05d5aba008ab96385f41398f001f
```

## 结果判断

子命令结果写为 stdout JSON：`ok` 表示操作返回状态。建模进度写入 stderr。退出码非零代表失败；不要仅凭生成了文件就报告成功。

模型验收还需检查 `result.passed` / 输出目录中的 `verification.json`。`accepted:true, completed:false` 的低层操作只表示消息已提交，必须读取后续窗口、控件或文件验证实际完成。

例子成功后读取：

- `model-with-results.svu`：可用 SystemView 直接打开的原生模型。
- `verification.json`：数值与导出检查。
- `output.csv`：AMI 时域数据；`output-spectrum.csv`：单边 dBm 功率谱。
- `ami-fft-example.png`：原生黑底黄线双边幅度谱，显示范围 ±1600 Hz。
- `ami-fft-example-full.csv`：全部 5001 个双边频点。

范例里的 “Cx FFT: Mag” 是线性幅度谱，不等同于 dBm 功率谱。比较图形之前对齐分析类型、单位和坐标范围。PN 随机序列不同会改变谱峰细节。AMI 示例保留原 JK 电路的一个启动码元，检查首 20 ms 输出为零及之后的交替极性。

## 定制电路

复制 `recipes` 中的通用配方，改节点位置、参数、命名端口和导出选择。用新目录运行 `model build`。模块参数的数字键是原生字段 ID，含义随模块变化，查接口指南及实际参数标签。

已有工程先复制到工作目录再操作：

```bat
sv.cmd start "work\copy.svu"
sv.cmd tokens
sv.cmd params 3
sv.cmd run
sv.cmd plots
sv.cmd export w2 "out\wave.csv"
sv.cmd export-png w2 "out\wave.png"
```

不要照抄其他工程的图元编号或 `wN`。多端口连线用实际端口名，例如 `Set*`、`Clock`、`Q`。

未知模块没有内置数值验收逻辑，时间轴检查通过不能证明电路正确。应为任务增加独立的数学检查。

## 本地数据和故障

`SV5_HOME` 可指定配置与运行目录；`SV5_EXE` 可临时指定程序路径；`SV5_PYTHON` 可指定 Python。运行内容、会话和输出可能含本机路径或注册信息，不要上传这些文件。

失败时用输出目录的 `session.json` 和 `inspect --children` 检查本工具创建的会话。不要无差别终止用户的其他进程，不要自动点击未知模态提示。完整参数见 [INTERFACE.md](INTERFACE.md)。
