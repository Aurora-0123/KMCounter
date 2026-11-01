# KMCounter — Windows 后台版

基于 [SilentDeep/KMCounter](https://github.com/SilentDeep/KMCounter) 的个人 fork。
保留键盘／鼠标热力图与历史趋势，增加托盘、登录自动启动和本机网页保护。
此分支面向 Windows x86_64，保留原项目 GPL-3.0 许可证。

## 安装与使用

解压重新构建的 `KMCounter-Windows.zip`，双击其中的 `install.cmd`。
程序安装到当前用户的 `%LOCALAPPDATA%\Programs\KMCounter`，完成后立即后台运行，
以后登录 Windows 时自动启动，不打开控制台或浏览器，不需要管理员权限。
安装器及托盘开关通过 Windows 系统注册表服务登记并回读确认启动项，避免安装宿主的隔离视图导致误判。

- 点击任务栏右下角的 KMCounter 图标打开统计，也可访问 http://127.0.0.1:5000 。
- 右键托盘图标可暂停／继续、关闭登录启动、打开数据目录或退出。
- 关闭统计网页仍继续记录；“退出程序”会先保存数据，再停止统计。
- 页面默认显示今天，每 5 秒刷新。手动选择起止时间后保留该范围；勾选实时更新恢复刷新结束时间。
- Windows 可能把图标放在任务栏的隐藏图标区域。

旧数据导入：在 PowerShell 中执行 `scripts/install.ps1 -LegacyData "旧版的 data 目录"`，
或对解压包中的 `install.ps1` 使用同一参数。更新前先从旧版托盘退出；原版 1.2 可用其网页 STOP 按钮退出。
安装器保留旧数据备份，新版不会删除原文件。与仓库原压缩包完全相同的示例记录不导入。
重叠分钟中相同按键取较大计数，不相加，因此重复导入不会翻倍。

个人数据在 `%LOCALAPPDATA%\KMCounter\data`，按天保存 JSON。
每 5 秒原子写盘，正常暂停和退出时保存。异常断电可能丢失最近约 5 秒记录。
备份个人数据时复制该目录；程序包和 Git 提交不包含个人统计。
`%LOCALAPPDATA%\KMCounter\kmcounter.log` 记录启动、托盘就绪及正常退出，不记录按键内容，方便排查登录启动。
如果文件损坏，程序保留原文件并显示错误，不会用空文件覆盖它；请从备份恢复后重新启动。

## 隐私与安全

仅保存每分钟的规范按键次数、鼠标按钮次数和归一化点击位置，不保存逐次按键序列、
完整输入文本、窗口标题、剪贴板或截图。统计文件仍可能反映字符频次和使用习惯，属于个人数据。
按键名称采用 Windows 虚拟键及固定映射，字段排序后写盘，不保存字符首次出现顺序。
Fn 等未被系统报告的键无法统计；长按键盘按键产生的系统重复事件会计数。

服务仅监听 `127.0.0.1:5000`，校验 Host，拒绝跨站来源；暂停和退出接口要求启动时生成的
随机令牌和同源请求。图表脚本本地提供，关闭云端导出，用 CSP 限制外部资源与连接。
程序不主动上传统计，离线可用。网页保护针对浏览器跨站请求；其他本机程序及本机账户仍可能访问
loopback 统计接口，同一用户或管理员下的程序还可直接读取本地统计文件。
服务端和页面使用更新的锁定依赖；二进制从此分支源码重新构建，尚未购买数字签名证书。

目前验证覆盖自动计数、并发、跨日、导入、写入失败、浏览器功能和网络请求。
真实重新登录后的自启动需要另行验证，不能用手动启动代替。
安全审查与验证记录见 [docs/security-review.md](docs/security-review.md)。

## 从源码运行与构建

使用已打补丁的 Windows Python 3.13.18 或更新的兼容版本，创建独立环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/build_windows.py
.\scripts\install.ps1 -LegacyData ".\release\KMCounter_v1.2_Windows_x86_64\data"
```

构建产物在 `release/KMCounter-Windows.zip`；构建脚本仅打包明确列出的程序资源和许可证。
开发运行 `python main.py --show` 打开页面，`--background` 后台运行，
`--enable-autostart` 开启登录启动，`--disable-autostart` 关闭后退出。
`--data-dir` 指定数据目录仅供独立测试；自启动使用默认个人数据目录。
重复启动只打开已有实例，不会重复计数。端口被其他程序占用时明确报错，不启动输入监听。

浏览器集成测试需要本机 Chrome 和可用的 5000 端口；测试使用合成数据，不启动全局输入监听。
后台图标与键鼠监听仅在当前用户的交互桌面会话中运行，不统计登录界面或其他用户会话。
原项目说明保存在 [docs/README-upstream.md](docs/README-upstream.md)。
