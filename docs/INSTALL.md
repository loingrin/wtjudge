# 安装与维护说明

适用于 wtjudge v1.1.1，Windows 10/11 x64。首次使用请先阅读 [README](../README.md) 中的下载、MinGW-w64、资料结构和使用步骤。

## Python 与依赖排查

Release 程序包自带 Python 运行依赖；本节仅适用于源码运行。

### 选择正确的解释器

建议使用已验证的 Python 3.12 x64，最低 Python 3.11。官方入口是 [Python Windows 下载页](https://www.python.org/downloads/windows/)。选择 64 位正常安装方式，安装 pip；传统安装器可启用 Python Launcher 和 PATH 选项。不要使用 embeddable package 代替正常开发环境。

若安装的是官网当前提供的 **Python Install Manager**，安装管理器后在 PowerShell 中执行下列命令获取 3.12；传统安装器用户跳过。两种安装方式均按后续命令检查实际版本和位数。参考 [Python 官方 Windows 说明](https://docs.python.org/3/using/windows.html)。

```powershell
py install 3.12
```

安装后关闭并重新打开 PowerShell，再检查：

```powershell
py --list
py -3.12 --version
py -3.12 -c "import sys, struct; print(sys.executable); print(struct.calcsize('P') * 8)"
```

输出应是预期解释器路径和 `64`。若 `py` 不可用，可以尝试：

```powershell
Get-Command python -ErrorAction SilentlyContinue
where.exe python
python --version
python -c "import sys, struct; print(sys.executable); print(struct.calcsize('P') * 8)"
```

如果 `python` 打开 Microsoft Store，检查 Windows“管理应用执行别名”和实际安装位置。可直接用解释器完整路径代替命令，例如 `& 'C:\Python312\python.exe' --version`，但需改成自己真实的安装路径。

### 创建与使用虚拟环境

在含有 `app.py`、`requirements.txt` 和 `setup.bat` 的源码根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

也可在创建 `.venv` 后双击 `setup.bat` 安装依赖，再双击 `run.bat` 启动。脚本复用已有 `.venv` 并检查版本与位数；没有虚拟环境时会优先使用 `py -3`，因此机器上装有多个 Python 时建议先按上述命令指定 3.12。

无需执行 `Activate.ps1`，因此不需要修改 PowerShell 执行策略。所有 pip 命令都通过虚拟环境内的 Python 执行，避免依赖装到另一个环境。

检查依赖是否安装完整：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import PySide6, psutil, openpyxl; print('Dependencies OK')"
```

`ModuleNotFoundError` 通常表示依赖未装入当前解释器。`No matching distribution found` 时核对 Python 版本、64 位架构、网络和软件包源；本项目并未验证所有更新的 Python 大版本。虚拟环境从另一台电脑复制、移动位置或更换基础 Python 后，应在新的源码目录重新创建，不要复用旧 `.venv`。

### 依赖下载失败或需要离线安装

先检查代理、网络与 pip 的错误信息。不要通过关闭证书校验来绕过 HTTPS 错误。

离线电脑应与联网准备电脑使用相同的 Windows 架构和 Python 小版本。在联网电脑的项目虚拟环境中下载：

```powershell
.\.venv\Scripts\python.exe -m pip download -r requirements.txt -d wheels
```

把源码和整个 `wheels/` 文件夹复制到离线电脑，在离线电脑创建 `.venv` 后执行：

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\wheels -r requirements.txt
```

`requirements.txt` 用于常规安装，`requirements-lock.txt` 记录维护者验证环境的具体依赖版本。独立测试环境需要再安装 `requirements-dev.txt`。

## 编译器排查

wtjudge 使用 GNU G++，执行 GNU++14 编译。MSVC 的 `cl.exe`、WSL 内的 Linux G++、MSYS 环境的编译器或单独复制来的 `g++.exe` 不能替代完整的 MinGW-w64 工具链。

### PATH 中没有 g++

在 PowerShell 中执行：

```powershell
Get-Command g++ -ErrorAction SilentlyContinue
where.exe g++
```

两条都找不到时，先检查已有 IDE 或工具链安装目录。wtjudge 不依赖全局 PATH，直接在界面选择完整路径即可，例如 `C:\msys64\ucrt64\bin\g++.exe`。命令行检查带空格的路径需要 PowerShell 调用运算符 `&`：

```powershell
& 'C:\msys64\ucrt64\bin\g++.exe' --version
& 'C:\msys64\ucrt64\bin\g++.exe' -dumpmachine
```

目标应是 x86_64 Windows，例如 `x86_64-w64-mingw32`。随后在软件中点击“验证编译器”，完成实际试编和试运行；仅能输出版本号不足以证明工具链可用。

### 没有 MinGW-w64

按 [README 的 MSYS2 安装步骤](../README.md#没有编译器使用-msys2-ucrt64)操作。MSYS2 的 `pacman` 命令必须在 **MSYS2 UCRT64 终端**中运行；Python 安装、`.bat` 脚本和 wtjudge 的手动命令使用 **Windows PowerShell**。二者不是同一个命令环境。

### 缺少 DLL、能编译但不能运行

不要从其他电脑或网站随意拷贝同名 DLL。保留同一套工具链的完整目录；MSYS2 用户按官方方式完整升级并安装 UCRT64 GCC。wtjudge 为编译和学生进程的 PATH 前置所选编译器的 `bin` 目录，以便查找配套 DLL；这不会修改系统 PATH。

若仍失败，检查验证窗口中的完整诊断，例如 `libstdc++-6.dll`、`libgcc_s_seh-1.dll`、`libwinpthread-1.dll` 缺失、可执行文件被安全软件隔离或目录无写权限。使用新建的普通可写文件夹复核，并查看安全软件的实际记录；无需授予软件管理员权限或全局关闭防护。

## 考试与结果排查

| 现象 | 检查方法 |
|---|---|
| 未识别某位考生 | 选择的是考生目录的父目录；每个考生应是其直接子文件夹 |
| 未识别某题或测试点 | `testdata/题名/` 下直接存放同名成对 `.in/.out`，不要多套一层目录 |
| 测试数据错误阻止开始 | 查看“检查详情”，补齐输入输出对，消除同名冲突，重新检查资料 |
| 缺源码或源码歧义 | 核对题名/源码名；为中文别名、多个 `.cpp` 等情况使用“指定源码…”明确关联 |
| 所有点都是 CE | 双击题目成绩查看编译诊断，检查学生语法、头文件和 Windows 兼容性 |
| 控制台能看到答案却是 NO_OUTPUT | 该软件评测文件 I/O；核对学生程序 `freopen` 和题目配置的完整输出名 |
| 全部或部分点 WA | 核对标准答案、比较模式、实际输入输出名称和程序算法；不要修改学生代码来凑答案 |
| TLE 在重复运行间变化 | 使用墙钟时间，进程启动、后台负载和安全扫描均可能影响；在目标电脑校准时限 |
| 结果显示不完整 | 排查 SYSTEM_ERROR、CANCELLED、未解决映射或其他无效项，修复后重评整批 |
| 打开项目后没有旧成绩 | 项目 JSON 保存配置；成绩请查看之前导出的 Excel/CSV/HTML/results.json |
| 无法导出 | 检查输出目录写权限、磁盘空间，以及 Excel 是否正在占用同名文件 |

每次导出创建新的 `wtjudge-时间戳/` 子目录。CSV 使用 UTF-8 BOM，考生 ID 和 Excel 中的前导零均作为文本保存。HTML 报告内嵌样式和 logo，可离线查看。请保留原始考试资料、配置 JSON 和完整导出目录，便于追查结果。

软件日志通常位于 `%LOCALAPPDATA%\wtjudge\wtjudge\logs\`（实际以 Qt 用户目录为准）。反馈问题时建议提供软件版本、Windows 版本、G++ 版本和目标、错误文本及能复现问题的最小示例；公开提交前删除考生姓名、个人路径与考试资料。

## 测试与打包

在源码根目录创建好 `.venv` 后安装测试依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:WTJUDGE_GXX = 'C:\msys64\ucrt64\bin\g++.exe'
.\.venv\Scripts\python.exe -m pytest
```

把编译器路径替换为本机已验证路径。没有可用 G++ 时部分集成测试会跳过；“跳过”不能当作已验证通过。维护者已在本机执行功能、真实数据复核与成绩配色测试，其他电脑仍需先通过编译器验证并运行内置演示。

打包：

```powershell
.\.venv\Scripts\python.exe tools/package_release.py
```

也可双击 `build.bat`。打包工具先构建到专用 `build/release/`，再发布到新的 `dist/wtjudge-1.1.1/`；同版本目录存在时追加时间戳。不要直接对存放考试资料的旧目录运行 PyInstaller 覆盖构建。

发布采用 onedir 结构，分发时压缩**整个目录**，包含 EXE、`_internal/`、说明和演示资料。目标电脑不需要 Python，仍需另装 MinGW-w64。不要把 `.venv/`、构建缓存、个人考试、学生提交或成绩报告上传到公开仓库/Release。

## 评测指标与边界

- 每个考生每题只编译一次：`g++ -std=gnu++14 -O2 -pipe -o program.exe source.cpp`，不修改学生源文件，不合并多个源文件，不使用 `-static`。
- 每个测试点使用全新工作目录；输入复制到题目配置的输入名，程序退出后比较指定输出文件。控制台输出仅用于诊断。
- 时间为真实墙钟时间，包含进程创建与初始化；编译和答案比较不计入单点运行时间。内存采用 Windows Job 峰值提交内存，不等同于 Linux RSS。
- 默认忽略 CRLF/LF、行末空格/Tab 和末尾空白行；严格模式按字节比较，单词模式忽略 ASCII 空白差异。
- 默认输出上限为 64 MB，监测指定输出文件、标准输出及标准错误的总和；属于定期采样的软阈值，快速写入可能短暂超过。
- 停止和超时会结束受控进程树；临时文件短暂被占用时重试，无法清理会给出路径并继续后续提交。请按实际提醒处理，不要删除仍在使用中的目录。
- Job Object 不是安全隔离：学生程序拥有当前用户权限。仅使用可信提交；评测不可信代码时应使用独立虚拟机或 Windows Sandbox。

相关官方资料：[MSYS2 安装](https://www.msys2.org/)、[更新](https://www.msys2.org/docs/updating/)、[环境选择](https://www.msys2.org/docs/environments/)、[Qt for Python 安装](https://doc.qt.io/qtforpython-6/gettingstarted.html)、[Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。
