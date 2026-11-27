#!/usr/bin/env python3
"""ctf-toolkit —— 把一堆 CLI 工具收进一个本地 Web 界面。

  toolkit                 # 起服务并打开浏览器
  toolkit --port 9000     # 换端口
  toolkit --no-browser    # 只起服务
  toolkit new-challenge demo --cat pwn   # 生成题目工程
  toolkit test-challenge demo            # compose 起停 + 端口冒烟

零第三方依赖（仅标准库 + tomllib）。工具清单在 tools.toml，改完刷新页面即生效。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
STATE = Path(os.environ.get("XDG_STATE_HOME") or (HOME / ".local/state")) / "ctf-toolkit"
LOGS = STATE / "logs"
LOGS.mkdir(parents=True, exist_ok=True)

MAX_LINES = 60000          # 内存里保留的输出行数上限
DROP_CHUNK = 20000         # 超限时一次丢弃的行数
MAX_LOG_BYTES = 32 * 1024 * 1024   # 单个 run 的磁盘日志上限（防止大输出撑爆磁盘）
KEEP_LOG_BYTES = 8 * 1024 * 1024   # 超限后保留的尾部字节数
TAIL_READ_BYTES = 8 * 1024 * 1024  # 回放只读文件尾部这么多字节
TRUNC_MARK = "[… 前部输出已丢弃（磁盘日志上限）…]\n".encode()
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")   # 进度条/颜色码，落库前剥掉
RUN_ID_RE = re.compile(r"[0-9a-f]{12}")   # Run.id 的形状；同时挡住 replay/export 的路径穿越

CATEGORIES = {
    "recon": "探测",
    "brute": "爆破",
    "vuln": "漏洞利用",
    "local": "本地/辅助",
}

# ───────────────────────────── 配置加载 ─────────────────────────────

def load_config() -> dict:
    with open(ROOT / "tools.toml", "rb") as f:
        cfg = tomllib.load(f)
    cfg.setdefault("app", {})
    tools = []
    for t in cfg.get("tool", []):
        t.setdefault("mode", "argv")
        t.setdefault("icon", "•")
        t.setdefault("view", "form")
        t.setdefault("presets", [])
        t.setdefault("notes", "")
        t.setdefault("cmd", [])
        fields = []
        for f in t.get("fields", []):
            f.setdefault("flag", "")
            f.setdefault("kind", "text")
            f.setdefault("label", f.get("flag") or "参数")
            f.setdefault("ph", "")
            f.setdefault("hint", "")
            f.setdefault("default", "")
            f.setdefault("options", [])
            f.setdefault("repeat", False)
            f.setdefault("req", False)
            fields.append(f)
        t["fields"] = fields
        t.pop("fields_php", None)
        tools.append(t)
    return cfg | {"tool": tools}


_WL_CACHE: dict = {"sig": None, "items": []}   # 文件 (mtime, size) 签名变了才重新数行数


def wordlists() -> list[dict]:
    d = ROOT / "wordlists"
    if not d.is_dir():
        return []
    try:
        paths = sorted(d.glob("*.txt"))
        sig = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    except OSError:
        return _WL_CACHE["items"]
    if sig == _WL_CACHE["sig"]:
        return _WL_CACHE["items"]
    out = []
    for p in paths:
        try:
            with p.open("rb") as f:
                n = sum(1 for _ in f)
        except OSError:
            n = 0
        out.append({"path": f"wordlists/{p.name}", "label": f"{p.name}（{n} 行）"})
    _WL_CACHE["sig"] = sig
    _WL_CACHE["items"] = out
    return out


def trim_log_file(path: Path, max_bytes: int = MAX_LOG_BYTES,
                  keep_bytes: int = KEEP_LOG_BYTES) -> None:
    """磁盘日志超限时只保留最后 keep_bytes，按行边界切（宁可多丢半行）。"""
    try:
        size = path.stat().st_size
        if size <= max_bytes:
            return
        with path.open("rb") as f:
            f.seek(max(0, size - keep_bytes))
            tail = f.read()
        nl = tail.find(b"\n")
        if nl >= 0:
            tail = tail[nl + 1:]
        tmp = path.with_name(path.name + ".tmp")   # 原子替换：并发 replay/export 不会读到写了一半的文件
        try:
            tmp.write_bytes(TRUNC_MARK + tail)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    except OSError:
        pass


def tail_lines(path: Path, max_bytes: int = TAIL_READ_BYTES,
               max_lines: int = MAX_LINES) -> list[str]:
    """只读日志尾部，避免回放/大日志把整文件读进内存。"""
    size = path.stat().st_size
    with path.open("rb") as f:
        cut = size > max_bytes
        if cut:
            f.seek(size - max_bytes)
        data = f.read()
    if cut:
        nl = data.find(b"\n")
        if nl >= 0:
            data = data[nl + 1:]
    return data.decode("utf-8", "replace").splitlines()[-max_lines:]


# ───────────────────────────── 运行管理 ─────────────────────────────

class Run:
    def __init__(self, tool_id: str, title: str, cmdline: str, argv: list[str], cwd: str,
                 ok_codes: tuple[int, ...] = (0,)):
        self.id = uuid.uuid4().hex[:12]
        self.tool_id = tool_id
        self.title = title
        self.cmdline = cmdline
        self.argv = argv
        self.cwd = cwd
        self.ok_codes = ok_codes        # 有些工具用非 0 退出码表示"正常"（ysoserial 列链 = 64）
        self.status = "running"          # running / done / failed / killed
        self.rc: int | None = None
        self.started = time.time()
        self.ended: float | None = None
        self.lines: list[str] = []
        self.dropped = 0
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.log_path = LOGS / f"{self.id}.log"

    @property
    def elapsed(self) -> float:
        return (self.ended or time.time()) - self.started

    def add(self, line: str):
        with self.lock:
            self.lines.append(line)
            if len(self.lines) > MAX_LINES:
                del self.lines[:DROP_CHUNK]
                self.dropped += DROP_CHUNK

    def slice_from(self, idx: int) -> tuple[list[str], int]:
        with self.lock:
            skip = max(0, idx - self.dropped)
            return self.lines[skip:], self.dropped + len(self.lines)

    def meta(self) -> dict:
        return {
            "id": self.id, "tool_id": self.tool_id, "title": self.title,
            "cmdline": self.cmdline, "cwd": self.cwd, "status": self.status,
            "rc": self.rc, "started": self.started, "elapsed": round(self.elapsed, 1),
            "lines": self.dropped + len(self.lines),
        }


RUNS: dict[str, Run] = {}
HISTORY_FILE = STATE / "history.jsonl"
HISTORY: list[dict] = []
START = time.time()
_HIST_APPENDS = 0          # 会话内每 50 条把 history.jsonl 重写一次，防止长会话文件无限涨


def load_history():
    if HISTORY_FILE.exists():
        for line in HISTORY_FILE.read_text(errors="replace").splitlines():
            try:
                HISTORY.append(json.loads(line))
            except ValueError:
                pass


def _rewrite_history():
    try:
        HISTORY_FILE.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in HISTORY))
    except OSError:
        pass


def append_history(rec: dict):
    global _HIST_APPENDS
    HISTORY.append(rec)
    del HISTORY[:-300]
    _HIST_APPENDS += 1
    try:
        with HISTORY_FILE.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if _HIST_APPENDS % 50 == 0:
        _rewrite_history()


# ───────────────────────────── 命令拼装 ─────────────────────────────

def subst(s: str, target: str) -> str:
    # {{ROOT}} 让 tools.toml 能直接指向本仓库的启动器，不依赖 ~/.local/bin 的软链
    s = s.replace("{{ROOT}}", str(ROOT))
    if target and "{{TARGET}}" in s:
        return s.replace("{{TARGET}}", target)
    return s


def tgt_value(f: dict, target: str) -> str:
    """主字段留空时用顶部目标框填：占位符里有 {{TARGET}} 就代入，否则取主机名。"""
    ph = f.get("ph") or "{{TARGET}}"
    if "{{TARGET}}" in ph:
        return ph.replace("{{TARGET}}", target)
    s = target if "//" in target else "//" + target
    return urlsplit(s).hostname or target


def abs_wordlists(tokens: list[str]) -> list[str]:
    """把 wordlists/ 开头的相对字典路径换成绝对路径（工作目录不是仓库根目录时也能用）。"""
    wd = str(ROOT / "wordlists")
    return [wd + "/" + t[len("wordlists/"):] if t.startswith("wordlists/") else t for t in tokens]


def build(tool: dict, values: list, extra: str, target: str) -> tuple[list[str], str]:
    """把表单值拼成 argv。返回 (argv, 人类可读命令行)。"""
    args: list[str] = []
    for i, f in enumerate(tool["fields"]):
        raw = values[i] if i < len(values) else f.get("default", "")
        if f.get("tgt") and not str(raw or "").strip() and target:
            raw = tgt_value(f, target)      # 顶部目标框自动填主字段
        if f.get("kind") == "bool":
            if raw in (True, "1", "true", "on", 1):
                if f.get("flag"):
                    args.append(f["flag"])
            continue
        if isinstance(raw, bool):
            raw = "1" if raw else ""
        val = subst(str(raw or ""), target).strip("\n")
        if not val.strip():
            continue
        if f.get("repeat"):
            for ln in val.splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                if f.get("flag"):
                    args += [f["flag"], ln]
                else:
                    args.append(ln)
            continue
        if f.get("flag"):
            args += [f["flag"], val]
        else:
            args.append(val)
    if extra and extra.strip():
        args += shlex.split(subst(extra.strip(), target))

    if tool["mode"] == "shell":
        parts = []
        for i, f in enumerate(tool["fields"]):
            raw = values[i] if i < len(values) else ""
            if isinstance(raw, (bool, int)):
                raw = "1" if raw else ""
            if f.get("tgt") and not str(raw or "").strip() and target:
                raw = tgt_value(f, target)
            raw = subst(str(raw or ""), target).strip()
            if not raw:
                continue
            parts.append(raw if f.get("raw") else shlex.quote(raw))
        if extra and extra.strip():
            parts.append(subst(extra.strip(), target))
        # shell 模式把整段拼成一条命令交给 bash；字典相对路径在这里一次性替换掉
        args = [" ".join(parts).replace("wordlists/", str(ROOT / "wordlists") + "/")]
    argv = [subst(c, target) for c in tool["cmd"]] + abs_wordlists(args)
    pretty = " ".join(shlex.quote(a) for a in argv)
    return argv, pretty


def spawn(tool: dict, values, extra: str, target: str, cwd: str) -> Run:
    argv, pretty = build(tool, values, extra, target)
    if not argv or not any(a.strip() for a in argv[len(tool["cmd"]):]):
        if not tool.get("allow_empty"):
            raise ValueError("没有任何参数——至少填一个字段或用预设")

    cwd_p = Path(os.path.expanduser(cwd or "~")).resolve()
    if not cwd_p.is_dir():
        raise ValueError(f"工作目录不存在: {cwd_p}")

    ok = tuple(tool.get("ok_codes", (0,)))
    run = Run(tool["id"], tool["name"], pretty, argv, str(cwd_p), ok)
    env = os.environ.copy()
    env["PATH"] = f"{HOME / '.local/bin'}:{env.get('PATH', '/usr/bin:/bin')}"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TERM", "dumb")

    if tool.get("strip_proxy"):
        # 环境里的 socks 代理会让内置 httpx/requests 直接 ImportError（缺 socksio），
        # 这类工具自己有 --proxy 字段，宁可让它不带代理跑
        for k in ("http_proxy", "https_proxy", "all_proxy", "ftp_proxy",
                  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY"):
            env.pop(k, None)
    else:
        # 从桌面启动时环境里没有代理变量，按配置补一个（工具要出网时靠它）
        p = CFG.get("app", {}).get("proxy_env", "")
        if p and not any(env.get(k) for k in ("http_proxy", "HTTP_PROXY")):
            env["http_proxy"] = env["https_proxy"] = env["HTTP_PROXY"] = env["HTTPS_PROXY"] = p

    if not _SLOTS.acquire(blocking=False):
        raise ValueError(f"并发已满（最多 {MAX_CONCURRENT} 个同时跑），先停几个再试")

    try:
        run.proc = subprocess.Popen(
            argv, cwd=str(cwd_p), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, errors="replace", bufsize=1,
            start_new_session=True, env=env,
        )
    except FileNotFoundError as e:
        _SLOTS.release()
        raise ValueError(f"命令不存在: {argv[0]} ({e})") from e
    except OSError as e:
        _SLOTS.release()
        raise ValueError(f"启动失败: {e}") from e

    RUNS[run.id] = run

    def pump():
        log = None
        try:
            log = run.log_path.open("w", errors="replace")
            written = 0
            assert run.proc and run.proc.stdout
            for line in run.proc.stdout:
                line = ANSI_RE.sub("", line)
                run.add(line.rstrip("\r\n"))
                log.write(line)
                log.flush()
                written += len(line.encode("utf-8", "replace"))
                if written > MAX_LOG_BYTES:      # 大输出：裁掉前部，只留尾部，避免磁盘无限涨
                    log.close()
                    trim_log_file(run.log_path)
                    log = run.log_path.open("a", errors="replace")
                    written = KEEP_LOG_BYTES
            rc = run.proc.wait()
            run.rc = rc
            run.ended = time.time()
            run.status = ("done" if rc in run.ok_codes else "killed" if rc < 0 else "failed")
            run.add(f"\n[退出码 {rc}] {run.status} · 耗时 {run.elapsed:.1f}s")
            append_history(run.meta() | {"cmdline": run.cmdline, "cwd": run.cwd})
            trim_runs()
        finally:
            if log:
                log.close()
            _SLOTS.release()   # 无论正常/异常结束都释放并发名额

    threading.Thread(target=pump, daemon=True).start()
    return run


def terminate_runs(grace: float = 2.0) -> None:
    """退出时先 TERM，宽限期内不退再 KILL：忽略 SIGTERM 的工具不会变成孤儿。"""
    procs = [r.proc for r in list(RUNS.values()) if r.proc and r.proc.poll() is None]
    for p in procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.time() + grace
    while time.time() < deadline and any(p.poll() is None for p in procs):
        time.sleep(0.05)
    for p in procs:                     # 先全部 KILL，避免逐个等待把总时长拖过桌壳的 3s 上限
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    reap_deadline = time.time() + 0.5
    for p in procs:
        try:
            p.wait(timeout=max(0.01, reap_deadline - time.time()))
        except subprocess.TimeoutExpired:
            pass


# ───────────────────────────── HTTP ─────────────────────────────

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ctf-toolkit"

    # ---- 基础工具 ----
    def log_message(self, format, *a):  # noqa: A002 - 基类参数名
        if os.environ.get("TOOLKIT_DEBUG"):
            sys.stderr.write("%s %s\n" % (self.address_string(), format % a))

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def j(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def _same_origin_ok(self) -> bool:
        """防跨站打本地端口：POST 必须带自定义头（浏览器跨域要预检，我们不放开 CORS）。"""
        if self.headers.get("X-Requested-By") != "toolkit":
            return False
        origin = self.headers.get("Origin")
        if origin:
            host = self.headers.get("Host", "")
            if urlparse(origin).netloc != host:
                return False
        return True

    # ---- 路由 ----
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)

        if path in ("/", "/index.html"):
            return self.static(ROOT / "web" / "index.html", ROOT / "web")
        if path.startswith("/web/"):
            return self.static(ROOT / "web" / path[len("/web/"):], ROOT / "web")
        if path.startswith("/vendor/"):
            return self.static(ROOT / "vendor" / path[len("/vendor/"):], ROOT / "vendor")

        if path == "/api/state":
            cfg = reload_config()
            return self.j({
                "app": {"title": cfg["app"].get("title", "CTF Toolkit"),
                        "port": PORT, "uptime": round(time.time() - START, 1),
                        "root": str(ROOT)},
                "categories": CATEGORIES,
                "tools": cfg["tool"],
                "wordlists": wordlists(),
                "wordlists_dir": str(ROOT / "wordlists"),
                "workdir_default": cfg["app"].get("workdir_default", "~/ctf/evidence"),
                "workdir_cwd": os.getcwd(),
                "history": HISTORY,   # 全量（内存里最多 300 条），前端自己做搜索/分页
            })

        if path == "/api/poll":
            run = RUNS.get(q.get("id", [""])[0])
            if not run:
                return self.j({"error": "no such run"}, 404)
            try:
                idx = max(0, int(q.get("from", ["0"])[0]))
            except ValueError:
                return self.j({"error": "from 必须是非负整数"}, 400)
            new, nxt = run.slice_from(idx)
            return self.j({"lines": new, "next": nxt, "status": run.status,
                           "rc": run.rc, "elapsed": round(run.elapsed, 1)})

        if path == "/api/replay":
            rid = q.get("id", [""])[0]
            if not RUN_ID_RE.fullmatch(rid):
                return self.j({"error": "无效的 run id"}, 400)
            p = LOGS / f"{rid}.log"
            if not p.exists():
                return self.j({"error": "日志已不存在"}, 404)
            txt = tail_lines(p)
            return self.j({"lines": txt, "next": len(txt), "status": "done"})

        if path == "/api/kill":
            return self.j({"error": "用 POST"}, 405)

        return self.j({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        if not self._same_origin_ok():
            return self.j({"error": "拒绝：缺少 X-Requested-By 头"}, 403)
        d = self.body()

        if path == "/api/run":
            cfg = reload_config()
            tool = next((t for t in cfg["tool"] if t["id"] == d.get("tool")), None)
            if not tool:
                return self.j({"error": "未知工具"}, 400)
            try:
                run = spawn(tool, d.get("values") or [], d.get("extra") or "",
                            d.get("target") or "", d.get("cwd") or cfg["app"].get("workdir_default", "~"))
            except ValueError as e:
                return self.j({"error": str(e)}, 400)
            trim_runs()
            return self.j({"id": run.id, "cmdline": run.cmdline, "cwd": run.cwd})

        if path == "/api/stop":
            run = RUNS.get(str(d.get("id")))
            if not run or not run.proc or run.proc.poll() is not None:
                return self.j({"error": "没有在跑"}, 400)
            try:
                os.killpg(os.getpgid(run.proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            def hard():
                time.sleep(3)
                try:
                    if run.proc and run.proc.poll() is None:
                        os.killpg(os.getpgid(run.proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            threading.Thread(target=hard, daemon=True).start()
            return self.j({"ok": True})

        if path == "/api/stop_all":
            stopped = 0
            for run in list(RUNS.values()):
                if run.proc and run.proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(run.proc.pid), signal.SIGTERM)
                        stopped += 1
                    except ProcessLookupError:
                        pass
            def hard_all():
                time.sleep(3)
                for run in list(RUNS.values()):
                    if run.proc and run.proc.poll() is None:
                        try:
                            os.killpg(os.getpgid(run.proc.pid), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
            threading.Thread(target=hard_all, daemon=True).start()
            return self.j({"ok": True, "stopped": stopped})

        if path == "/api/export":
            rid = str(d.get("id") or "")
            if not RUN_ID_RE.fullmatch(rid):
                return self.j({"error": "无效的 run id"}, 400)
            run = RUNS.get(rid)
            src = run.log_path if run else LOGS / f"{rid}.log"
            if not src.exists():
                return self.j({"error": "日志不存在"}, 404)
            slug = (run.tool_id if run else "run")
            dst_dir = HOME / "ctf" / "evidence" / slug
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{rid}.log"
            shutil.copyfile(src, dst)
            return self.j({"path": str(dst)})

        return self.j({"error": "not found"}, 404)

    def static(self, p: Path, base: Path):
        base = base.resolve()
        try:
            p = p.resolve()
            if p.is_dir():
                p = (p / "index.html").resolve()   # 追加后必须重新 resolve，符号链接 index 也要落回 base
        except (OSError, ValueError):
            return self.j({"error": "not found"}, 404)
        # 用 is_relative_to 而不是 startswith：后者对「名字前缀相同」的同级目录会误判放行
        if not p.is_relative_to(base):
            return self.j({"error": "forbidden"}, 403)
        try:
            data = p.read_bytes()
        except (OSError, ValueError):
            return self.j({"error": "not found"}, 404)
        ext = p.suffix.lower()
        ctype = {
            ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8", ".json": "application/json",
            ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
            ".ico": "image/x-icon", ".wasm": "application/wasm", ".map": "application/json",
            ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
            ".txt": "text/plain; charset=utf-8",
        }.get(ext, "application/octet-stream")
        self._send(200, data, ctype)


CFG: dict = {}
CFG_MTIME: float = 0.0
PORT = 8787
MAX_RUNS = 40              # 内存里最多留多少个 run（更老的从 RUNS 里丢掉，磁盘日志还在）
KEEP_LOGS = 200            # 启动时保留最近多少个日志文件
MAX_CONCURRENT = 20        # 同时真正在跑的进程上限，超过直接报错（防止批量目标把机器打爆）
_SLOTS = threading.Semaphore(MAX_CONCURRENT)
STOP_SIGNALED = False      # SIGTERM 只处理一次：Tauri 与 systemd 可能各发一次


def _on_term(*_) -> None:
    """第一次 SIGTERM 触发正常退出；清理期间再来的信号直接忽略，避免打断兜底 KILL。"""
    global STOP_SIGNALED
    if STOP_SIGNALED:
        return
    STOP_SIGNALED = True
    raise SystemExit(0)


def reload_config() -> dict:
    """tools.toml 改了就直接生效：按 mtime 判断，解析失败继续用旧配置不把服务打挂。"""
    global CFG, CFG_MTIME
    p = ROOT / "tools.toml"
    try:
        m = p.stat().st_mtime
    except OSError:
        return CFG
    if m != CFG_MTIME:
        try:
            CFG = load_config()
            CFG_MTIME = m
        except Exception as e:                     # noqa: BLE001 - 配置坏了不能让服务挂
            sys.stderr.write(f"[warn] tools.toml 解析失败，继续用旧配置: {e}\n")
    return CFG


def trim_runs():
    """只保留最近的 MAX_RUNS 个 run 在内存里，避免长会话内存一路涨。"""
    if len(RUNS) <= MAX_RUNS:
        return
    finished = sorted((r for r in RUNS.values() if r.status != "running"),
                      key=lambda r: r.started)
    for r in finished[:len(RUNS) - MAX_RUNS]:
        RUNS.pop(r.id, None)


def prune_state():
    """清理历史日志与 history.jsonl，防止无限增长。"""
    logs = sorted(LOGS.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in logs[KEEP_LOGS:]:
        try:
            p.unlink()
        except OSError:
            pass
    if len(HISTORY) > 400:
        del HISTORY[:-300]
        _rewrite_history()


def main() -> int:
    global CFG, CFG_MTIME, PORT
    argv = sys.argv[1:]
    if argv and argv[0] in ("new-challenge", "test-challenge"):
        # 子命令只在 CLI 用；Web 模式不加载模板代码
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from challenge import cli as challenge_cli
        return challenge_cli(argv)

    ap = argparse.ArgumentParser(
        description="CTF Toolkit 本地 Web 界面",
        epilog="子命令:\n"
               "  toolkit new-challenge <name> --cat pwn|web|crypto|misc|reverse [--dest DIR]\n"
               "  toolkit test-challenge <dir> [--timeout 300]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--port", type=int, default=None, help="0 = 内核分配空闲端口（桌面壳用）")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--host", default="127.0.0.1", help="只允许回环地址；对外暴露需再加 --allow-remote")
    ap.add_argument("--allow-remote", action="store_true", help="允许绑定非回环地址（危险）")
    a = ap.parse_args(argv)

    CFG = load_config()
    CFG_MTIME = (ROOT / "tools.toml").stat().st_mtime
    PORT = a.port if a.port is not None else int(CFG["app"].get("port", 8787))
    load_history()
    prune_state()

    if a.host not in ("127.0.0.1", "localhost", "::1"):
        if not a.allow_remote:
            print(f"拒绝绑定 {a.host}：这个界面能在本机执行任意命令，只允许回环地址。\n"
                  f"确实要对外暴露，加 --allow-remote（风险自负）。", file=sys.stderr)
            return 2

    # 桌面壳（Tauri）关窗口时发 SIGTERM：走正常退出路径，finally 里清理工具进程
    signal.signal(signal.SIGTERM, _on_term)

    httpd = ThreadingHTTPServer((a.host, PORT), Handler)
    PORT = httpd.server_address[1]   # --port 0 时拿内核分配的真实端口（桌面壳从 stdout 读）
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{PORT}/"
    # stdout 被桌面壳管道捕获时默认全缓冲，必须立即交出端口完成启动握手。
    print(f"ctf-toolkit · {len(CFG['tool'])} 个工具 · {url}", flush=True)
    print("Ctrl-C 退出")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        # 清理期间屏蔽重复 SIGTERM/SIGINT：第二次信号不能打断 terminate_runs 的宽限与兜底 KILL
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        httpd.server_close()
        terminate_runs()
    return 0


if __name__ == "__main__":
    sys.exit(main())
