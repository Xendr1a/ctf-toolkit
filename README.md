# CTF Toolkit

把散落在 `~/.local/bin`、`~/ctf/tools`、docker 镜像里的命令行工具收进**一个本地网页**：
左栏点工具 → 表单填参数 → 「▶ 运行」→ 输出实时流回页面。不用记 flag，命令行可以一键复制回终端。

- 纯本地：只监听 `127.0.0.1`，无第三方依赖（Python 标准库 + `tomllib`）
- 19 个工具 / 4 个分类，每个都带**预设**（列库、拖表、目录爆破、JWT 攻击、SSTI、PHP gadget…）
- 顶部「目标」框自动填主字段（`{{TARGET}}` 占位符）
- 输出实时流式显示，可停止、可导出到 `~/ctf/evidence/`
- 历史记录（近 300 次），点一条即可回看输出
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

自测（会自己起一个本地 PHP 靶站，把 curl / whatweb / ffuf / sqlmap / phpggc / shell 六条链路真跑一遍）：

```bash
python3 selftest/smoke.py          # 6/6 通过 === 一切正常
python3 selftest/smoke.py --keep   # 跑完不关靶站，方便自己点着玩
```

## 工具清单（`tools.toml`）

| 分类 | 工具 | 定位 |
|---|---|---|
| 探测 | `curl` `whatweb` `httpx` `nmap` | 手工请求、指纹、存活探测、端口 |
| 爆破 | `ffuf` `dirsearch` `gobuster` | 目录/子域/参数 |
| 漏洞利用 | `sqlmap` `nuclei` `dalfox` | SQLi、模板扫描、XSS |
| 漏洞利用 | `fenjing` | SSTI（直接打或用 payload 模式） |
| 漏洞利用 | `jwt_tool` `phpggc` `php_filter_chain` `ysoserial` | JWT、PHP/Java 反序列化、filter chain |
| 本地/辅助 | `静态服务` `nc 监听` `自由命令` `CyberChef` | 起站、收 shell、任意命令、编解码 |

工具本体不搬家，注册表只记「怎么调」：

- `cmd = [...]` 绝对命令（可以是 `php .../phpggc`、`java -jar ...`、`~/ctf/.venv/bin/python ...`）
- `mode = "shell"` 时把表单内容拼成一行交给 `bash -lc`，适合管道/重定向
- 字段 `tgt = true` 表示「顶部目标框留空时自动填这个字段」；占位符里的 `{{TARGET}}` 会被替换，无占位符则取主机名
- `presets` 只是往「附加参数」里塞字符串，塞完还能改，不藏魔法

### 加一个新工具

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

存盘 → 刷新页面即生效（服务端每次 `/api/state` 都重读 `tools.toml`）。

## 目录

```
toolkit.py        # 服务端：注册表加载、命令拼装、进程管理、HTTP/API（~430 行，标准库）
tools.toml        # 工具注册表（要加工具改这里）
web/              # 前端（原生 JS，无构建步骤）
wordlists/        # 自带字典，UI 里下拉可选（gitignored，用 fetch-vendor.sh 拉）
vendor/cyberchef/ # 离线 CyberChef v11.6.0（gitignored，用 fetch-vendor.sh 解包）
scripts/          # fetch-vendor.sh
selftest/         # 自测：本地 PHP 靶站 + 6 条链路的断言脚本
bin/toolkit       # 启动器
```

运行日志落在 `~/.local/state/ctf-toolkit/logs/<run-id>.log`，「导出」会复制一份到 `~/ctf/evidence/<工具>/`。

## 说明 / 坑

- **沙箱**：`ctfrun`/`ctfdbg`（firejail）是「跑样本」用的，这里**不沙箱**——这些工具本来就要连外网。
- **nmap 没 root**：宿主机匿名用户无 `CAP_NET_RAW`，`-sS/-sU/-O` 会失败，注册表默认 `-sT`；要 SYN 扫描用 `ctfbox nmap -sS`（容器内是 root）。
- **httpx 是 ProjectDiscovery 版**（`-u` 不是 `curl`），别和 Python 的 httpx 混淆。
- **jwt_tool 用 `~/ctf/.venv/bin/python` 跑**（宿主 python 缺 `ratelimit`）；ysoserial 已自带 `--add-opens`，JDK 27 上能跑。
- **安全**：服务只绑 `127.0.0.1`；所有 POST 要求 `X-Requested-By: toolkit` 头并校验 `Origin`，防别的网页跨域打你本地端口执行命令。别把它绑到 `0.0.0.0`。
- 只能打授权目标。比赛平台本身不在范围内（这条是用户明确要求）。
