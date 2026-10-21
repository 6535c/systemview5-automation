# SystemView 5 接口使用指南

## 1. 运行环境与安装

- 正常的 Windows 桌面会话，Python 3.10+，Windows .NET Framework 4.x。
- 合法可用的 ELANIX SystemView 5.0 Build046；应安装在当前用户可运行的位置。
- 版本校验为 EXE 文件 SHA256：`82f1a0f823450dcf9439370c3e7c601e99da05d5aba008ab96385f41398f001f`。
- 系统可为 64 位，桥接助手是 32 位，因为目标软件为 32 位。
- 本包不含原版软件、许可证、注册信息、厂商 DLL 或既有 `.svu` 模板。

下载 Release ZIP 并解压。便携运行即可；可选 `powershell -File install.ps1 -Destination "X:\Tools\SystemView5Automation"`，安装程序校验清单后复制到新目录，不写系统设置或 PATH。

```bat
sv.cmd config --exe "X:\YourInstallation\SysVu_32.exe"
sv.cmd doctor
sv.cmd version
```

设置 `SV5_PYTHON` 可选择解释器，`SV5_EXE` 可临时覆盖程序路径，`SV5_HOME` 可重定向本地配置与运行目录。未设置时使用当前用户本地应用数据目录。配置和运行记录不在发布包里。

## 2. 完整配方流程

```bat
sv.cmd model build "recipes\ami.json" --out "out\ami-001"
sv.cmd model build "recipes\multiply.json" --out "out\product-001" --keep-open
sv.cmd model lab1 --out "out\lab1-001"
sv.cmd model verify "out\ami-001"
```

`build` 从运行中的软件自行新建空白工程，逐个添加和定义模块、按端口连线、设置时间、保存模型，再在新会话加载该模型进行仿真和导出。将两个阶段分开以减少旧版 VB6 的窗口状态残留。默认保存结果后关闭所创建的进程，`--keep-open` 留在设计窗供检查。

`lab1` 顺序执行三套通用示例。`verify` 只重新检查本地导出数据，不启动仿真器。输出目录必须不存在，图形和工程另存命令也拒绝覆盖现有文件。出现未知提示或数值错误时，命令失败并保留诊断状态。

程序有单实例转交行为，启动新工程可能被转交给已运行的实例。工具会预检查并拒绝此情况；请先自行保存并关闭其他实例。

### 配方结构

```json
{
  "schema":1,
  "name":"Example",
  "timing":{"fs":10000,"start":0,"stop":0.5},
  "nodes":[
    {"id":"pn","kind":"source","at":[100,100],"choice":"PN Seq","params":{"21":1,"42":50,"44":2,"46":0,"48":0}},
    {"id":"sink","kind":"sink","at":[400,100],"choice":"Analysis"}
  ],
  "edges":[{"from":"pn","to":"sink"}],
  "outputs":{"signal":"sink"},
  "spectra":["signal"]
}
```

`at` 为画布逻辑坐标，不是鼠标屏幕坐标。`id` 用于配方引用；软件实际图元号由软件创建后读取。支持 `source`、`operator`、`function`、`logic`、`sink`、`adder` 和 `multiplier`。`choice` 必须是实际库标签；加法器和乘法器无需 `choice`。

多端口连接：

```json
{"from":"high","to":"jk","port":"Set*"}
{"from":"jk","to":"derivative","out_port":"Q"}
```

参数键是原生数字字段 ID。常见映射：

| 模块 | 字段 ID → 含义 |
| --- | --- |
| PN Seq | 21 幅度，42 码率，44 电平数，46 偏置，48 相位 |
| Pulse Train | 21 幅度，42 频率，44 脉宽，46 偏置，48 相位 |
| Step Fct | 21 幅度，42 阶跃时刻 |
| And / Not | 21 阈值，42 真输出，44 假输出 |
| Derivative / Hold | 21 增益 |
| Sampler | 21 采样率，42 孔径，44 抖动 |
| FF-JK* | 21 门延时，42 阈值，44 真输出，46 假输出，48 上升时间，50 下降时间 |

`operations.json` 保存实际参数控件和标签，可用于核对。`verification` 为可选内置数值检查类型：`nrz-rz`、`ami`、`multiply`。省略时只检查时间轴，不表示电路逻辑已验证。

## 3. 功率谱与范例式 FFT

`spectra` 产生原生 Sink Calculator 的 `Power Spectrum (dBm in 1 ohm)`：单边、dBm，Mixed Radix、不补零。对 5001 点时域波形导出 2501 个频点。检查直流分量、频率轴和 Parseval 功率关系。

范例中的 `Cx FFT: Mag` 是双边线性幅度谱。可添加：

```json
"fft_views":[{"name":"ami-fft-example","signal":"output","xlim":[-1600,1600],"ylim":[0,2000]}]
```

此流程使用原生 Complex FFT，实数输入、虚部为零、Magnitude 输出、Mixed Radix，无补零。软件对正向 FFT 乘以 `1/Fs`。再用原生 Set Min/Max 设置显示范围，导出彩色 WMF，并渲染真实图形控件为黑底黄线 PNG。全部频点单独保留在 `*-full.csv`，显示缩放不篡改数据。

FFT 检查包含直接 DFT 抽查、实信号共轭对称及 Parseval 关系。PN 序列不同会改变峰高与细节，不能用是否逐像素相同来判断电路。

AMI 示例的微分增益为 1，输出幅度为 ±Fs，默认即 ±10000。其 JK 链在首码元存在启动瞬态；配方显式声明 `verification_options.startup_symbols=1`，检查首 20 ms 输出零，再核对后续 24 个码元。此示例不是无启动瞬态的完整线路编码器。

## 4. 已有工程命令

```bat
sv.cmd start "work\copy.svu"
sv.cmd tokens
sv.cmd params 3
sv.cmd param-set 3 "Amplitude (v 0-p)" 2
sv.cmd run
sv.cmd plots
sv.cmd export w2 "out\wave.csv"
sv.cmd export-image w2 "out\wave.wmf"
sv.cmd export-png w2 "out\wave.png"
sv.cmd save-as "out\changed.svu"
sv.cmd close
```

| 命令 | 作用 |
| --- | --- |
| `start FILE` | 启动目标进程并打开 `.svu`，可用 `--exe` 临时指定安装路径 |
| `tokens` | 读取图元号和真实模块说明 |
| `params ID` | 读取模块的原生数字参数和链接 |
| `param-set ID NAME VALUE` | 使用原生常量全局参数链接提交数值并读回 |
| `param-clear ID NAME` | 清除指定参数的全局链接 |
| `run` / `plots` | 运行仿真 / 列出真实分析窗 |
| `export wN FILE.csv` | 原生导出 X/Y，保留 `.sv.txt` 并转成 CSV |
| `export-image wN FILE.wmf` | 原生矢量导出并检查 WMF 完整性 |
| `export-png wN FILE.png` | 渲染经验证的原生图形控件，保留屏幕颜色 |
| `save-as FILE.svu` | 原生另存并核对完整字节数及标题 |
| `inspect --children` | 读取窗口、控件和实际软件反馈 |
| `menus` / `menu PATH` | 列出或提交原生菜单命令 |
| `set-text HWND VALUE` / `click HWND` / `select HWND INDEX` | 低层控件操作 |
| `close` | 请求正常关闭；未保存提示仍需按实际内容处理 |

指定会话须放在子命令之前：

```bat
sv.cmd --state "out\product-001\session.json" inspect --children
```

`wN`、图元号、参数名必须从当前工程读取。`export-png` 会调整本会话中的图形布局并最大化该图形。低层消息提交不能证明动作完成；文字设置不能替代参数 Validate/Evaluate 提交。

## 5. Python API

在工具根目录的 Python 环境中：

```python
from svctl import Session
from svapi.model import Model

s = Session("out/session.json")
m = Model(s, initial_count=6)  # 必须是当前真实图元数量
m.connect(0, 3)
m.timing(fs=10000, start=0, stop=0.5)
```

`Model` 方法：`add(kind_number,x,y)`、`define(id,library,label,params)`、`connect(source,target,port=None,out_port=None)`、`timing`、`run(expected_sink_count)`、`spectrum`、`complex_fft`、`scale_view`、`close_analysis`。`Native` 是版本绑定的内部实现，不是稳定的通用 RPC。

推荐 `model build`，它管理新建、阶段切换、保存和关闭。自行调用需维护模态事件返回、空工程图元计数及 native bridge 生命周期；完成后先关闭分析窗再调用 `m.n.stop()`。

## 6. 输出、隐私和故障

结果为 stdout JSON，进度为 stderr，退出码非零表示失败。`.svu` / `.wmf` 校验字节数；CSV 检查两列、有限数值、样本数和时间轴。`verification.json` 记录检查范围，不为未覆盖模块作保证。

输出文件可能包含本机绝对路径、注册信息或用户自定义内容。默认忽略规则防止常见运行文件进入 Git，但不能替代检查用户自行添加的文件。不要把输出目录、注册过的软件或凭据加入发布包。

| 情况 | 处理 |
| --- | --- |
| 未配置 / 哈希不匹配 | 配置真实 `SysVu_32.exe`；不同二进制不支持，不绕过校验 |
| 启动 `code 5` | 在正常交互桌面运行；隔离服务或沙箱桌面可能不可用 |
| 已有实例 | 保存并关闭其他 SystemView 后重试 |
| 模态提示 / 超时 | 对本次 `session.json` 使用 `inspect --children`；不要盲点未知提示 |
| 软件退出 / 导出失败 | 保留本地诊断；用新输出目录重新执行，不覆盖已经保存的工程 |
| 缺少某库 | 检查合法安装的组件；本包不提供厂商库或许可证 |

不支持任意 SystemView 版本、所有模块、复杂滤波器编辑或无桌面的服务器运行。助手只加载到经 PID、进程创建时间、路径和二进制 SHA256 核对的目标进程，不修改安装文件，也不直接改写模型内存字段。
