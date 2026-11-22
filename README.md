# CTF Toolkit

把散落在 `~/.local/bin`、`~/ctf/tools`、docker 镜像里的命令行工具收进**一个桌面应用**（Tauri 原生窗口，也可纯浏览器模式）：
左栏点工具 → 表单填参数 → 「▶ 运行」→ 输出实时流回页面。不用记 flag，命令行可以一键复制回终端。

- 纯本地：只监听 `127.0.0.1`；浏览器模式零依赖（Python 标准库 + `tomllib`），桌面模式用系统 webview（webkit2gtk）
- 27 个工具 / 4 个分类，专注 Web；每个都带**预设**（列库、拖表、目录爆破、JWT 攻击、SSTI、PHP gadget、爬站…）
- 顶部「目标」框自动填主字段（`{{TARGET}}` 占位符）；逗号/换行分隔可一次打多个目标
- 输出实时流式显示，可停止、可导出到 `~/ctf/evidence/`
- 历史记录（近 300 次），点一条即可回看输出
- 多任务并行：每次运行开一个标签页，各自独立实时流；切标签回看，关运行中标签 = 停止它；历史回放也开标签
- 内置 CyberChef（离线单页版，`vendor/cyberchef/`）
- 内置字典 `wordlists/`：SecLists 的 `common.txt`、`raft-small-directories/words`

```
┌─ 目标 [http://10.0.0.5:8080] ─ 工作目录 [~/ctf/evidence] ┐
│ 探测   🌐 curl        ┌ sqlmap ────────────────┐         │
│        🔎 whatweb     │ -u  [http://10.0.0.5…] │  ▶ 运行 │
│ 爆破   💥 ffuf        │ --dbms [mysql ▾]       │  ■ 停止 │
│ 利用   🗄️ sqlmap      │ ☑ --batch              │  复制   │
│        ☢️ nuclei      │ 预设: 探注入点 列库 …   │         │
│ 本地   🧰 CyberChef   └────────────────────────┘         │
│                       [ 输出流 … ]                       │
└──────────────────────────────────────────────────────────┘
```

## 安装 / 启动

### 桌面模式（Tauri 原生窗口，推荐）

```bash
npm install                        # 装 @tauri-apps/cli（仅构建期）
npx tauri build                    # 出 src-tauri/target/release/ctf-toolkit（~8MB）
bash scripts/install-desktop.sh    # 软链 ~/.local/bin/ctf-toolkit + 应用菜单入口
```

应用菜单（fuzzel/rofi）或 `ctf-toolkit` 启动。壳自动起 Python 后端子进程（内核分配端口），
关窗口 / Ctrl-C / kill 都会回收后端；后端自己死了窗口自动关。指向别的仓库用 `TOOLKIT_ROOT=/path/to/repo`。
构建依赖：Rust ≥1.77、node、webkit2gtk-4.1 / gtk3 / libsoup3（Arch 官方源都有）。

### 浏览器模式（零依赖）
```bash
# 重新拉外部资源（字典 + 离线 CyberChef、约 80MB；这俩不进 git）
bash scripts/fetch-vendor.sh

# 已经在用的话
toolkit                 # 起服务 + 开浏览器（默认 http://127.0.0.1:8787/）
toolkit --port 9000     # 端口被占时换一个
toolkit --no-browser    # 只起服务

# 换机器/新克隆
ln -sf "$PWD/bin/toolkit" ~/.local/bin/toolkit
```

自测（两套，跑完都绿就说明基础链路没坏）：

```bash
python3 -m unittest discover -s selftest -t .   # 19 个单测：拼命令/目标替换/字典路径/run 淘汰/桌面握手/路径安全
python3 selftest/smoke.py                       # 6/6 通过 === 端到端链路都通
python3 selftest/smoke.py --keep                # 跑完不关靶站，方便自己点着玩
```

## 工具清单（`tools.toml`）

| 分类 | 工具 | 定位 |
|---|---|---|
| 探测 | `curl` `whatweb` `httpx` `nmap` | 手工请求、指纹、存活探测、端口 |
| 探测 | `katana` `waybackurls` `subfinder` `dnsx` `amass` | 爬站 / 历史 URL / 子域与资产枚举 |
| 探测 | `wafw00f` `arjun` | WAF 识别 / 隐藏参数发现 |
| 爆破 | `ffuf` `dirsearch` `gobuster` `feroxbuster` | 目录/子域/参数 |
| 漏洞利用 | `sqlmap` `nuclei` `dalfox` | SQLi、模板扫描、XSS |
| 漏洞利用 | `fenjing` | SSTI（直接打或用 payload 模式） |
| 漏洞利用 | `jwt_tool` `phpggc` `php_filter_chain` `ysoserial` | JWT、PHP/Java 反序列化、filter chain |
| 本地/辅助 | `静态服务` `nc 监听` `自由命令` `CyberChef` | 起站、收 shell、任意命令、编解码 |

工具本体不搬家，注册表只记「怎么调」：

- `cmd = [...]` 绝对命令（可以是 `php .../phpggc`、`java --add-opens ... -jar ...`、`jwt` 这种包装脚本）
- `mode = "shell"` 时把表单内容拼成一行交给 `bash -lc`，适合管道/重定向
- 字段 `tgt = true` 表示「顶部目标框留空时自动填这个字段」；占位符里的 `{{TARGET}}` 会被替换，无占位符则取主机名
- `presets` = 先重置表单 → 用 `set` 填字段（键可用序号/flag/标签）→ `args` 进「附加参数」，仍可手改，不藏魔法

### 加一个 Web 工具（3 步，不用改代码）

1. 在 `tools.toml` 末尾粘一段（照抄现成条目最省事）：

```toml
[[tool]]
id = "nikto"
name = "nikto"
category = "vuln"          # recon / brute / vuln / local
icon = "🕵️"
desc = "经典 Web 扫描器"
notes = "-Tuning 调整测试项；-ssl 走 https"
cmd = ["nikto"]
fields = [
  { flag = "-h", label = "目标", kind = "text", ph = "{{TARGET}}", tgt = true },
  { flag = "-Tuning", label = "测试项", kind = "text", ph = "123b" },
  { flag = "-ssl", label = "-ssl", kind = "bool" },
]
presets = [ { label = "常规扫描", args = "-h {{TARGET}} -Tuning 123b" } ]
```

2. **校验语法**（Inline table 必须在一行内，这是最容易踩的）：

```bash
python3 -c "import tomllib;d=tomllib.load(open('tools.toml','rb'));print(len(d['tool']),'tools ok')"
```

3. **刷新页面**就多一个工具（服务端按 mtime 热重载，不用重启）；填个目标点运行，看输出对不对。

字段速查：`kind` 支持 `text` / `textarea` / `select`(`options`)/ `bool`(`default="1"` 勾上)/ `combo`
(`options_from="wordlists"` 出字典下拉)/ `number`；`flag` 留空 = 位置参数；`repeat = true` = 一行一个参数；
`tgt = true` = 顶部目标自动填（一个工具只标一个）；要跑管道就 `mode = "shell"` + 一个 `raw = true` 的字段。

工具级两个开关（踩过坑才有）：
`ok_codes = [0, 64]` = 哪些退出码算成功（ysoserial 列链返 64、fenjing 没打到返 1，别让页面标成"失败"）；
`strip_proxy = true` = 丢掉环境里的 `http(s)/all_proxy`（python 系工具遇到 socks 代理会直接 `ImportError: socksio`，这类工具请用表单里的 `--proxy`）。
完整 schema 见 `tools.toml` 文件头的注释。

## 目录

```
toolkit.py        # 服务端：注册表加载、命令拼装、进程管理、HTTP/API（~430 行，标准库）
tools.toml        # 工具注册表（要加工具改这里）
web/              # 前端（原生 JS，无构建步骤）
wordlists/        # 自带字典，UI 里下拉可选（gitignored，用 fetch-vendor.sh 拉）
vendor/cyberchef/ # 离线 CyberChef v11.6.0（gitignored，用 fetch-vendor.sh 解包）
scripts/          # fetch-vendor.sh / install-desktop.sh
src-tauri/        # Tauri 桌面壳（Rust：后端子进程管理 + 原生窗口）
package.json      # 构建期依赖 @tauri-apps/cli
selftest/         # 自测：本地 PHP 靶站 + 6 条链路的断言脚本
bin/toolkit       # 启动器
```

运行日志落在 `~/.local/state/ctf-toolkit/logs/<run-id>.log`，「导出」会复制一份到 `~/ctf/evidence/<工具>/`。

## 说明 / 坑

- **沙箱**：`ctfrun`/`ctfdbg`（firejail）是「跑样本」用的，这里**不沙箱**——这些工具本来就要连外网。
- **nmap 没 root**：宿主机匿名用户无 `CAP_NET_RAW`，`-sS/-sU/-O` 会失败，注册表默认 `-sT`；要 SYN 扫描用 `ctfbox nmap -sS`（容器内是 root）。
- **httpx 是 ProjectDiscovery 版**（`-u` 不是 `curl`），别和 Python 的 httpx 混淆。
- **jwt_tool 用 `~/ctf/.venv/bin/python` 跑**（宿主 python 缺 `ratelimit`）；ysoserial 已自带 `--add-opens`，JDK 27 上能跑。
- **安全**：服务只绑 `127.0.0.1`（绑定其他地址会被直接拒绝，除非显式 `--allow-remote`）；所有 POST 要求
  `X-Requested-By: toolkit` 头并校验 `Origin`，防别的网页跨域打你本地端口执行命令。别把它对外暴露。
- **只能打授权目标**。比赛平台本身不在范围内（这条是用户明确要求）。
- **热重载**：`tools.toml` 存盘即生效（服务端按 mtime 重读）；改坏了会打一条 warn 并继续用旧配置，不会把服务打挂。
- **状态清理**：运行日志保留最近 200 个（启动时清理），`history.jsonl` 超 400 条自动裁剪到 300；
  内存里最多留 40 个 run（更老的丢内存，磁盘日志按保留策略走）。
- **桌面壳**：窗口加载后端回环端口，安全模型与浏览器模式完全相同；壳只管进程生命周期。
  二进制搬出仓库时从可执行文件目录向上找 `tools.toml`，找不到用 `TOOLKIT_ROOT` 指定。

## 已知限制 / 还能优化的

| 优先 | 事项 | 现状 |
|---|---|---|
| P1 | pwn/逆向/取证 没上界面 | gdb、checksec、binwalk、exiftool、hashcat 只能走「自由命令」，加进 `tools.toml` 即可做成表单 |
| P2 | 无鉴权 | 只靠回环 + 自定义头；同一台机器上任何本地进程都能调 API |
| P2 | 输出只留在本地 | 没有把命中结果自动汇总成 writeup 片段；导出是原始日志 |
| P3 | 无 worker 复用 | 多目标会起多个独立进程（各自一个标签），不共享 worker；大批量会占用多进程 |
