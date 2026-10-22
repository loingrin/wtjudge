# 第三方软件与许可证

wtjudge 使用下列第三方软件，各组件版权归原作者所有，分别遵循其自身许可。本文件只说明第三方组件，不为 wtjudge 的原创代码或 wotu 标识另行指定许可证。

发行包随附的 [`third_party/`](../third_party/) 目录保存实际安装包中的许可证及官方上游文本。[`manifest.json`](../third_party/manifest.json) 记录各文本的来源及 SHA256；[`DEPENDENCIES.json`](../third_party/DEPENDENCIES.json) 记录实际构建环境中的依赖版本和许可元数据。该目录中的许可证文本保留原文，未改写条款。

## 运行依赖

| 组件 | 此次构建版本 | 许可与随附说明 |
| --- | --- | --- |
| CPython | 3.12.14 | Python Software Foundation License 及历史许可；见 `third_party/Python/LICENSE.txt` 和 `Doc-license.rst`。未修改 Python 本身。 |
| PySide6、PySide6 Essentials、Shiboken6、Qt | 6.12.0 | Qt/PySide 的开源许可包含 LGPLv3 等选项；见 `third_party/Qt/LGPL-3.0-only.txt`、`GPL-3.0-only.txt`、`GPL-2.0-only.txt` 及下述 Qt 说明。商业许可原文仅保留上游元数据所附的说明，不表示本项目持有商业许可。 |
| psutil | 7.2.2 | BSD 3-Clause，见 `third_party/psutil/LICENSE`。 |
| openpyxl | 3.1.5 | MIT，见 `third_party/openpyxl/LICENCE.rst`。 |
| et_xmlfile | 2.0.0 | MIT 及其所附 Python 来源说明，见 `third_party/et_xmlfile/`。 |
| OpenSSL | 3.5.8 | Apache License 2.0，见 `third_party/OpenSSL/LICENSE.txt`；作为 Python 扩展的依赖随 Windows 包分发。 |

Python 的标准库扩展也可能使用 Expat、zlib、libffi、bzip2、XZ/liblzma 等组件；对应版权和许可见 `third_party/Python/Doc-license.rst`。Windows 包包含的 Microsoft Visual C++ 运行库仍适用 [Microsoft 运行库许可](https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/)。MinGW-w64/GCC 由用户单独安装，wtjudge 不附带编译器。

## Qt 与动态库

wtjudge 使用 Qt for Python 构建界面。Qt、PySide 和 Shiboken 的版权包括 The Qt Company Ltd. 及其贡献者；组件的准确版权归属保留在官方源代码及随附的版权记录中。

Windows 包采用目录分发，Qt/PySide/Shiboken 动态库放在 `_internal/PySide6/` 和 `_internal/shiboken6/`。未修改这些库，也未增加阻止替换动态库的完整性校验。需要调试或使用修改后的、接口兼容的库时，可在副本中替换对应 DLL/PYD 和必要插件；应保持 Python ABI、Qt 版本接口及依赖一致。也可依照安装文档从源码运行并使用自行构建的 PySide/Qt。LGPL 覆盖部分的修改以及为调试这些修改而进行的逆向工程，应按照 LGPL 条款保留相应权利。

上游许可与对应版本源代码：

- [Qt 许可说明](https://doc.qt.io/qt-6/licensing.html) 与 [Qt for Python 第三方许可](https://doc.qt.io/qtforpython-6/licenses.html)。
- [PySide/Shiboken 6.12.0 源代码](https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.12.0)。
- [Qt 6.12.0 源码下载](https://download.qt.io/official_releases/qt/6.12/6.12.0/single/) 与 [Qt Base v6.12.0](https://github.com/qt/qtbase/tree/v6.12.0)。
- [Qt Image Formats v6.12.0](https://github.com/qt/qtimageformats/tree/v6.12.0) 与 [Qt SVG v6.12.0](https://github.com/qt/qtsvg/tree/v6.12.0)。

Qt 内部还包含第三方实现。本次随附 `third_party/Qt/qtbase/` 和 `third_party/Qt/qtimageformats/` 中的上游 `qt_attribution.json` 及其许可证原文，以保留版权姓名、许可和来源。记录也可能包含同一模块中按平台或构建选项启用的组件，不代表这些组件在每台 Windows 机器上均启用。完整的上游组件索引见 [Qt 使用的第三方代码](https://doc.qt.io/qt-6/licenses-used-in-qt.html)。

This software is based in part on the work of the [FreeType Project](https://freetype.org/) and the Independent JPEG Group. 对应 FreeType、libjpeg-turbo、PNG、HarfBuzz、PCRE2 等原作者声明保留在上述目录的许可文本与版权记录中。

## 构建工具

PyInstaller 6.22.3 使用 GPL 及其 Bootloader Exception；例外原文保存在 `third_party/pyinstaller/licenses/COPYING.txt`，其中也说明运行时钩子的 Apache 2.0 许可。本文件不把 PyInstaller 的 GPL 许可套用到 wtjudge 的原创代码。

另外随附此次构建所用 pyinstaller-hooks-contrib、altgraph、packaging、pefile、pywin32-ctypes 和 setuptools 的实际许可证，分别位于同名子目录。它们主要用于构建环境，并非所有工具均进入最终程序。各组件的准确版本见 `third_party/DEPENDENCIES.json`。

重新打包或升级依赖时，应同步检查和更新本目录中的版本、版权文本与来源清单。
