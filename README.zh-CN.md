# DCC-MCP FilmCraft

用于控制同一个可见 FilmCraft WebAssembly 编辑器的实验性、带类型的浏览器 SDK。
[English](README.md)

首批交付是浏览器集成组件，尚不是已发布的 Core 适配器。它调用官方
window.filmcraft API，通过编辑器实际使用的 Rust 控制队列操作当前文档。
不会启动另一个 CLI 编辑器实例，也不会开放本机控制网关。

已验证的范围：
- 创建空项目、导入有大小限制的媒体、创建和重命名序列
- 调整视频与关联音频的播放速度，撤销、重做并读取时间线
- 保存原生 .fcproj 字节，校验完整性后从本会话虚拟路径重新打开
- 导出带音频的 H.264/MP4 与 WAV，查询或取消本客户端创建的任务
- 校验来源、Window/Document/API 会话身份、项目修订号与文件/任务所有权
- 拒绝路径穿越、重复路径、越界输入、未授权消息及重放
- 断开连接时保留文档；超时或中断等待后不自动重放可能已执行的操作

运行时为官方 FilmCraft v0.7.2，下载后校验 SHA-256。测试使用原创程序生成的
校准画面和音频，保存真实编辑器截图、浏览器录像、原生项目与导出媒体，并用
FFmpeg 验证慢放画面与音频结果。详见 [验收记录](docs/acceptance.md)。

使用时必须独占操作：上游没有原子的“检查修订号并执行”接口。请勿在自动化
期间手动切换或修改项目。SDK 的检查不是 UI 锁。请求发出后的超时或中断等待
不代表宿主操作已取消；应调用 reconcile() 等待原操作明确结束。
浏览器路径属于虚拟文件系统，不是操作系统路径。断开连接不会删除虚拟文件。

开发：npm ci --ignore-scripts；npm run check；npm test；npm run typecheck。
真实浏览器验收：安装 Playwright 1.55.0、其 Chromium 与 FFmpeg 后运行
python tests/browser-e2e.py。CHROMIUM_PATH 可选择兼容的已安装浏览器。

截至 2026-10-13，官方 13 个 Crafting Apps 都有浏览器 ZIP 发行文件；官网
“12 个支持浏览器”的列表已落后于发行状态。13 个根 Cargo.toml 都声明
MIT OR Apache-2.0，但这不是字体、素材、依赖和编解码器的完整许可审计。
浏览器 WASM 不等于 WASI，也不意味着所有应用都提供同样的自动化接口。

此组件没有复制整个上游仓库，没有发布、合并、部署或修改凭据。
PhotoCraft 与 PdfCraft 的现有适配器继续独立维护。
