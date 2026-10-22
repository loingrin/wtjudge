# wtjudge v1.1.1

Windows 10/11 64位本地C++14模拟赛批量评测工具。

## 下载与运行

- 推荐下载 **wtjudge-v1.1.1-windows-x64.zip**，解压全部文件后启动文件夹内的`wtjudge.exe`，不需要安装Python。
- 运行评测仍需本机MinGW-w64 G++。请在“题目配置”中选择`g++.exe`并点击“验证编译器”。完整安装及操作步骤见README和`docs/INSTALL.md`。
- `wtjudge-v1.1.1-source.zip`是源码包，需要Python及依赖。GitHub自动生成的Source code下载同样不是可直接运行的Windows程序。
- `SHA256SUMS.txt`列出下载文件校验值。压缩包中的`_internal/`是运行依赖，请保持整个目录完整。

## 本版内容

- 将已确认的磨砂浅色界面与成绩配色定版为v1.1.1。
- 0分白底；按得分比例显示三档绿色；满分使用更深绿色。
- AC绿、RE紫、CE橙黄、TLE/MLE近黑藏蓝。整题测试点完整且同一种错误时，成绩格直接显示对应代号。
- HTML、Excel报告同步配色。Excel显示错误代号时底层仍保留数值，CSV/JSON维持真实成绩。
- 增补新用户的Python、虚拟环境、MinGW-w64配置、演示考试及常见问题说明。
- 发布内容包括应用及合成演示，不包含真实学生提交、考试成绩或本机私人核验日志。

## 已知边界

仅支持Windows本地单源C++文件输入输出，不包含编译器、SPJ或交互题支持。评测记录Windows墙钟时间和Job提交内存，与官方Linux环境可能有差异。Job Object不隔离恶意程序，只应评测可信提交。
