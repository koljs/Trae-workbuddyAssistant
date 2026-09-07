# 更新日志

本文件记录 Trae Work Assistant 的版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

---

## [2.6.3] - 2026-09-07

修复 WorkBuddy 积分查询报"请求不合法"的问题：计费网关新上线的 User-Agent 校验拒绝 HTTP 库默认 UA。

### 修复

- **积分查询统一浏览器 User-Agent**（`src-tauri/src/workbuddy/http.rs`）：WorkBuddy 计费网关（`/v2/billing/meter/*`）自 2026-09-01 起校验请求的 `User-Agent`，无 UA 或携带 `ureq/<版本>` 等 HTTP 库默认 UA 的请求会被拒绝并返回"请求不合法"——这解释了 2.6.2 中全部「端点 × 认证通道」组合（请求头各不相同）一致失败的现象：它们的共同点是都经 ureq 发送、携带库默认 UA。现 WorkBuddy 模块统一 HTTP 客户端改用浏览器级 `User-Agent`（对齐官方 Electron 桌面端内核），覆盖积分、签到、token 刷新等全部 WorkBuddy 请求。签到接口此前未被该校验覆盖故未受影响，本次一并加固以防后续扩散。

---

## [2.6.2] - 2026-09-06

WorkBuddy 积分查询改为多通道自动探测 + 诊断日志，进一步排查"请求不合法"。

### 改进

- **多通道自动探测**（`src-tauri/src/workbuddy/credits.rs`）：单次积分查询依次尝试「端点 × 认证通道」四组合——①miniprogram 头 + 按 domain 端点（对齐官方小程序）②miniprogram 头 + 另一官方端点 ③web+桌面完整头 + workbuddy.cn ④web+桌面完整头 + codebuddy.cn（v2.6.0 行为）——任一组合成功即返回，适配不同账号/时期的网关策略；旧 `/v2` 接口回退保留。
- **错误信息透出**：全部组合失败时，错误消息汇总各组合的真实返回（此前只显示旧接口一条错误，掩盖了新接口的失败原因），悬停积分概览错误项即可查看完整内容。
- **诊断日志**：每轮查询把「成功的组合」或「各组合错误」追加写入 `data/logs/workbuddy_credits.log`（自动轮转，超 512KB 重建；不含 token），便于反馈排查。

---

## [2.6.1] - 2026-09-06

修复 WorkBuddy 积分概览刷新时报"请求不合法，如有疑问请联系客服"的问题。

### 修复

- **积分查询认证通道**（`src-tauri/src/workbuddy/credits.rs`）：WorkBuddy 用户中心的 billing 网关按 `X-Client-Platform` 声明区分认证方式——`web` 平台走 Cookie 认证（不携带 Authorization 头），`miniprogram` 平台走 `Authorization: Bearer <token>`。桌面端持有 OAuth token 却声明 `web` 平台，被业务层按 Cookie 通道校验并拒绝。现改为模拟官方小程序通道：声明 `X-Client-Platform: miniprogram` 并携带 Bearer token，同时请求头集合对齐官方用户中心 Axios 拦截器（仅 Authorization / X-Client-Platform / Content-Type / Accept，不再附带 X-User-Id、X-Domain 等桌面端专用头）。
- **旧接口回退通道**：`/v2/billing/meter/get-user-resource`（v2 前缀的桌面客户端 API）回退时改用与签到一致的桌面请求头，不再复用小程序通道头。

---

## [2.6.0] - 2026-09-06

新增 WorkBuddy 应用内自动签到：软件运行期间每日到点自动执行，无需手动点击。

### 新增

- **WorkBuddy 自动签到调度器**（`src-tauri/src/workbuddy/auto.rs`）：应用启动时常驻后台线程，每 30 秒检查一次；开关开启、到达设定时刻且当天尚未执行时，对「今日未签且未标记需重登」的 WorkBuddy 账号发起一键签到。复用手动签到的全部链路（token 惰性刷新、状态查询、签到日志、全局轮次锁），与手动签到天然互斥——自动触发撞上手动签到进行中时本轮放弃、下个周期自动重试。
- **设置项**：`Settings` 新增 `wb_auto_checkin`（开关，默认关闭）与 `wb_auto_checkin_time`（触发时间，默认 `09:00`）；设置页「每日定时签到」卡片内新增「WorkBuddy 自动签到」区块，随顶部「保存」按钮生效。
- **自动签到完成通知**：完成事件带 `source: "auto"` 标记，前端全局 Toast 提示「成功 X，已签 Y，失败 Z」，与手动签到（发起方提示）不重复；顶栏账号状态在任一轮签到完成后自动刷新。
- **执行状态持久化**：`data/workbuddy_auto_checkin.json` 记录最近一次执行日期与结果，防止同一天重复触发；「无账号 / 全部已签」不计入当日完成，当天稍后新增的账号仍可被自动签到。

### 说明

- 本功能为**应用内定时器**，仅软件运行期间生效（含最小化到托盘）；软件未运行的时段不补签。需要覆盖关机时段的场景请继续使用计划任务（当前计划任务仅支持 Trae 账号）。
- 应用在设定时刻之后启动时，若当天尚未自动签到且存在未签账号，会在启动后约 30 秒内补执行一次。

## [2.5.1] - 2026-09-04

修复便携包在未安装 Python 的机器上无法生成/安装 CA 证书的问题。

### 修复

- **便携包内嵌 Python 运行时**：`scripts/package_portable.py` 打包时自动构建并嵌入 Python 3.12 embeddable 解释器与依赖库（`cryptography`、`pywin32`、`cffi`、`pycparser`，解压至 `resources/python/Lib/site-packages/`），并重写 `python312._pth` 启用 `import site`。`state.rs` 原有逻辑会优先探测 `resources/python/python.exe`，便携包从此开箱即用，CA 证书生成（`device_proxy.py --gen-ca`）等全部 Python 功能不再依赖目标机器安装 Python。
- 首次打包时运行时缓存于 `release/_py_runtime/`（可复用），剔除 `PyWin32.chm` 帮助文档等无用文件控制体积。打包脚本在 Windows / Linux 主机上均可运行（pip 交叉下载 `win_amd64` wheels）。

### 说明

- 安装版（NSIS/MSI）维持 README 声明的前置要求"Python 3.9+"不变，行为未变。
- 便携包体积由约 7.4 MB 增至约 28 MB（内嵌运行时所致）。

## [2.5.0] - 2026-09-04

移除软件激活（授权口令）机制，应用启动后直接进入主界面，无需激活。

### 移除

- **激活门（前端）**：`src/components/ActivationGate.tsx`（口令输入页）与公众号二维码 `src/assets/wechat-qr.jpg`；`App.tsx` 启动时不再调用 `license_status` 检查授权，`src/lib/tauri.ts` 移除 `api.license` 封装。
- **授权防护（后端）**：`src-tauri/src/commands/license.rs`（`license_status` / `license_activate` 命令）与 `src-tauri/src/license_guard/` 模块（验证服务器通信、RSA 验签、机器指纹采集、本地凭证校验）。
- **依赖清理**：`Cargo.toml` 移除仅被授权模块使用的 `rsa`、`winreg`（`base64` / `sha2` / `ureq` 被其他模块使用，保留）。

### 说明

- 授权系统此前未写入任何文档（`docs/` 与 `README.md` 均无激活流程描述），故其余文档无需改动。
- 老用户本机 `%USERPROFILE%\.license_guard\license.dat` 残留凭证不再被读取，可手动删除。
- 正式版需重新执行 `npm run tauri build` 打包；开发模式 `npm run tauri dev` 直接生效。

---

## [2.4.4] - 2026-08-16

维护版本：清理临时文档并同步版本号。

### 变更

- 删除临时问题分析报告 `docs/issue-analysis-2026-08-16.md`，其功能已由 `CHANGELOG.md` 与 `AGENT.md` 中的变更说明覆盖，避免重复维护。
- 版本号 2.4.3 → 2.4.4（`package.json` / `tauri.conf.json` / `Cargo.toml` / `Cargo.lock` 四处同步）。
- 同步更新 `README.md`、`AGENT.md`、`docs/user-manual.md`、`docs/tech-framework.md`、`docs/operation-manual.md` 中的版本标注，以及 `scripts/make_portable_zip.py` 的便携包文件名。

### 说明

- 本版本**无代码逻辑改动**，仅文档与版本号维护；v2.4.3 的代理/VPN 共存与定时任务修复保持有效。
- 若需重新打包安装包，仍须执行 `npm run tauri build`（Python 侧修复已随 v2.4.3 打包）。

---

## [2.4.3] - 2026-08-16

修复「开启本地代理后 GitHub / Google 打不开」与「定时签到注册·查询·取消无反应」两类问题。

### 修复

- **本地代理与 VPN 冲突导致外网无法访问**（`ERR_TUNNEL_CONNECTION_FAILED`）
  - 根因：`proxy_start` 把 Windows 系统代理**整体覆盖**为 `127.0.0.1:8899`，抹掉了 VPN（Clash / v2rayN 等本地 HTTP/SOCKS 代理）的接管点；而 `tunnel_raw()` 对非 Trae 域名使用 `socket.create_connection` **直连**上游，完全绕开 VPN，导致 GitHub / Google 被阻断，而 baidu / qq 等国内站点直连可达故始终正常。
  - 修复：引入**上游代理链式转发**。`proxy_start` 在改写系统代理**之前**先读取已有的系统代理配置，作为 `UPSTREAM_PROXY` 环境变量注入 Python 代理进程；`device_proxy.py` 新增 `_parse_upstream()` / `connect_via_upstream()`，支持 **HTTP CONNECT** 与 **SOCKS5**（含用户名密码认证）两类上游。`tunnel_raw()` 与明文 HTTP 转发路径对**非 Trae 域名**优先经上游（即 VPN）出站，上游不可用时自动回退直连。Trae 域名仍由本代理 MITM 解密以捕获 JWT。
- **CONNECT 隧道缺少握手应答**
  - `tunnel_raw()` 从未向客户端回送 `HTTP/1.1 200 Connection Established`，客户端因此永远不会发起 TLS 握手；上游不可达时也无任何应答，浏览器无限等待。现已补齐 `200` 握手，失败时回 `502 Bad Gateway`。
- **停止代理会破坏 VPN 设置**
  - `proxy_stop` 原先只是把 `ProxyEnable` 置 0。现改为**原样还原**启动前捕获的系统代理（含 `ProxyServer` 与 `ProxyOverride`），停止本地代理后 VPN 立即恢复可用。
- **计划任务查询结果中文乱码**
  - 根因：`schtasks` 的中文输出为 **GBK** 编码，Rust 侧用 `String::from_utf8_lossy` 按 UTF-8 解读，产生 mojibake（如 `ϵͳ�Ҳ���ָ�����ļ���`，实为「系统找不到指定的文件」）；乱码进一步导致「找不到」关键字匹配失效，无法命中「任务未注册」的友好分支。
  - 修复：新增 `run_schtasks()` 统一入口，前置 `chcp 65001` 强制 schtasks 以 UTF-8 输出，中文错误信息可正确解码与匹配。
- **错误提示前缀重复**
  - 原先 Rust 返回 `查询计划任务失败：…`，前端 `Settings.tsx` 又拼接 `查询失败：`，叠加成「查询失败：查询计划任务失败：…」。现 Rust 端只返回纯错误文案，前端前缀成为唯一前缀。
- **定时任务注册在普通用户下失败**
  - 移除 `schtasks /RL HIGHEST`（签到脚本只读写 `%APPDATA%` 并运行 Python，无需提权，强制最高权限会让普通用户卡在 Access Denied）；`/TR` 命令行改为 `cmd /c set "TRAEDATA_DIR=…" && "<python>" "<script>"`，对含空格的路径安全。
- **查询 / 取消操作静默吞错误**
  - `task_status` 原先无论成功失败都返回 `Ok(stdout)`，任务不存在时返回空串，界面显示空白；`task_unregister` 原先丢弃执行结果永远返回 `Ok(())`。现均真实上报结果：任务不存在时返回明确提示「未注册每日签到任务（请先在设置页点击「注册任务」）。」，取消时若任务本就不存在按已删除处理。

### 变更文件

| 文件 | 说明 |
|---|---|
| `src-python/device_proxy.py` | 上游代理链式转发（HTTP CONNECT / SOCKS5）、`tunnel_raw` 补 `200` 握手与 `502` 兜底 |
| `src-tauri/src/commands/proxy.rs` | 启动前捕获系统代理并注入 `UPSTREAM_PROXY`、停止时原样还原、抽出 `apply_proxy` / `get_existing_win_proxy` |
| `src-tauri/src/commands/misc.rs` | 新增 `run_schtasks()`（`chcp 65001`）、去重复前缀、移除 `/RL HIGHEST`、错误可见性增强 |
| `docs/issue-analysis-2026-08-16.md` | 新增问题深度分析报告（调用链、根因、修复、验证方法） |

### 升级注意

`device_proxy.py` 会被打包进安装包的 `resources/python/`，**代理相关修复必须重新执行 `npm run tauri build` 才会进入正式版**；开发模式 `npm run tauri dev` 直接读取 `src-python/`，重启代理即生效。

---

## [2.4.2] - 2026-08-15

### 修复
- 修复发布版黑框 / 闪退 / 排队提醒丢失等 GUI 失灵问题。
- 健康检查端点统一为 `/health`，文档英文化与路径清理。
- 移除 `proxy_logs` 目录引用，日志统一存放在 `logs/` 下。
- 全面修复文档错误；恢复误删的 `src-python/tests/test_auto_checkin.py`。

### 新增
- 便携版打包脚本 `scripts/make_portable_zip.py` / `scripts/package_portable.py`。

---

## [2.4.1] - 2026-08-14

### 变更
- 项目重命名为 `trae-work-assistant`，同步更新文档与用户手册。

### 新增
- 账号切换流程重构、保存登录态能力、帮助说明。

### 修复
- 日志相关问题修复。

---

## [2.4.0]

- API 服务页面重构、日志页面整合与 UI 优化。

## [2.3.0]

- API 服务协议对齐、代理修复、交互优化与日志增强。

## [2.2.0]

- 全面质量优化：Mutex 安全锁（poison 恢复）、竞态修复、暗色模式图表适配、积分三线趋势图。

## [2.0.0]

- 本地 API 网关（axum + ureq）、SSE 协议转换、账号池智能调度、签到错误冷却状态机、6 层设备标识重置。
