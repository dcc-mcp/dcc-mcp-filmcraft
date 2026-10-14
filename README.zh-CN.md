# DCC-MCP FilmCraft

为 FilmCraft Web/WASM 和原生本地引擎提供实验性的 DCC-MCP Core 适配器、真正的 MCP stdio 服务，以及类型化浏览器 SDK。[English](README.md)

Python 适配器通过 Core 0.20.44 和官方 MCP SDK 提供 stdio 协议。浏览器模式注册 19 个工具，共享同一个编辑器页面；原生模式注册 18 个工具，共享一个官方 filmcraft-cli MCP 进程。两种模式分别提供 skill 和真实宿主验收。没有任意代码、任意宿主命令或 HTTP 控制网关。

## 使用

```sh
python -m pip install .
python -m playwright install chromium
dcc-mcp-filmcraft serve --runtime-zip /path/to/filmcraft-web-0.7.2.zip
```

在 MCP 客户端中配置上述 stdio 命令。默认打开可见编辑器；`--headless` 是显式自动测试选项。`--evidence-dir /path` 记录同一个页面，`--chromium /path` 可指定已安装的兼容 Chromium。`dcc-mcp-filmcraft status` 显示协议与运行时要求。

使用[官方 FilmCraft v0.7.2 浏览器 ZIP](https://github.com/storytold/filmcraft/releases/download/v0.7.2/filmcraft-web-0.7.2.zip)，SHA-256 必须为 `48d4f48728fa6b5c028612a4b7f59a5832ff38d430c6a7bd417a2c77d75ae4f9`。适配器不会自动下载或安装运行时。需要 Python >=3.10，Core >=0.20.44,<0.21。wheel 包含浏览器 SDK、桥接脚本、tools.yaml 与工作流 skill；MCP prompts/get 可获取 filmcraft-browser。

## 原生本地模式

```sh
dcc-mcp-filmcraft serve --mode native \
  --native-cli /path/to/filmcraft-cli --workspace /path/to/filmcraft-work
```

使用官方 FilmCraft 0.7.2 CLI，在一个持久化原生引擎中创建、导入、编辑、变速、撤销重做、保存和重开项目，以及导出视频/音频。它是无窗口的本地引擎，不等同于桌面 GUI。没有启动 TCP 控制端口。原生 MCP 提供 filmcraft-native 工作流和 18 个工具，不提供 filmcraft_capture_view；浏览器的 19 工具与截图能力保留。

启动参数中的工作目录由操作者指定，每个会话建立新的私有子目录。工具只接收本会话的虚拟路径和产物 ID。结束 stdio 后保留已保存的项目、导入媒体和导出文件；未保存的内存编辑随宿主进程结束。原生进程丢失后永久撤销执行，不会启动替代进程重放修改。

原生 CI 在执行前核验官方 Linux 发行包和 CLI 文件的 SHA-256；适配器不自动安装软件。当前真实原生宿主验收仅覆盖 Linux，跨平台单元测试不代表 macOS/Windows 宿主已实测。桌面 GUI 实际启动遇到云桌面 X11 共享内存绘制错误，尚未通过可用性/控制验收，也未接入适配器。[完整模式对照与边界](docs/native-mode.md)。

## 已实现能力

- 创建空项目、导入授权媒体字节、创建和重命名序列
- 对视频及关联音频变速、撤销/重做、读取真实时间线
- 保存原生 .fcproj，校验其完整性并在同一会话重新打开
- 原生导出 H.264/MP4（带音频）和 WAV，观察和取消本会话导出任务
- 只有成功结束的导出才能读取；文件以 SHA-256 产物 ID 返回，每次最多读取 256 KiB
- 捕获同一编辑器截图；保留超时/取消请求的原始回执
- 拒绝越界参数、额外参数、任意代码、非本会话文件或任务、路径穿越、覆盖和并行修改

媒体导入最多 16 MiB，单个导出产物读取最多 32 MiB（不是磁盘导出的硬配额），产物缓存总量最多 128 MiB。没有工具可读写任意操作系统路径或访问任意 URL。Core 调度前增加完整 JSON Schema 校验。

## 会话与安全边界

Playwright 的私有管道连接固定页面函数；导航后永久撤销执行权限。仅用于静态文件的 loopback 服务提供已校验的官方运行时与适配器脚本，没有命令、上传、文件浏览或代理路由。禁止跨来源网络请求。启动的是适配器自己的新浏览器页面，不会接管任意现有用户标签。

浏览器派发前取消不会执行。派发后取消/超时不等于宿主取消或回滚，必须核对原始回执，不得重试修改。回执核对只使用原页面保留的闭包；页面销毁时报告结果不确定，不能在新页面重新获得权限。

原生重开要求导入媒体仍在同一会话中；.fcproj 并非媒体打包文件。上游没有原子的版本比较并执行机制，工具工作时不要同时手动编辑。disconnect 只关闭类型化客户端并保留页面；终止 stdio 进程会关闭临时浏览器，请先读取所需产物。

这是未发行的有边界集成，没有实现 Core 网关发现、桌面 TCP、WASI 或跨重启恢复。未创建上游 fork、新凭证、release、merge 或部署。[MCP 验收证据](docs/mcp-acceptance.md)；[浏览器边界](docs/browser-boundary.md)。

## 验证

```sh
npm ci --ignore-scripts
npm run check && npm test && npm run typecheck
python -m pip install -e '.[dev]'
python -m pytest
python -m playwright install chromium
python tests/mcp-e2e.py --runtime-zip /path/to/filmcraft-web-0.7.2.zip
python tests/mcp-lifecycle.py --runtime-zip /path/to/filmcraft-web-0.7.2.zip
```

媒体验收需要 FFmpeg/ffprobe，使用自制校准视频和声音，独立解码验证变速后的图像和音频；不冒充主观听音验证。官方系列库存包含 13 个有浏览器发行包的 Crafting Apps，但并非每个都提供相同的 JS API。已有 PhotoCraft/PdfCraft 仓库继续复用。
