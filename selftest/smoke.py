#!/usr/bin/env python3
"""端到端自测：起一个本地 PHP 靶站，然后通过 toolkit 的 HTTP API 把几条常用链路真跑一遍。

  python3 selftest/smoke.py            # 自己起 toolkit（8788）＋靶站（8899）
  python3 selftest/smoke.py --port 8787  # 打到已经在跑的实例

每一步都断言真实输出，结果打表格。全部通过返回 0。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "selftest" / "www"


def free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_port(port: int, t=15.0):
    end = time.time() + t
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def api(port: int, path: str, body: dict | None = None, timeout=20):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Requested-By": "toolkit", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def run_tool(port: int, tool: str, values: list, extra: str, target: str, cwd: str, limit=180):
    """跑一个工具，返回完整输出。"""
    r = api(port, "/api/run", {"tool": tool, "values": values, "extra": extra, "target": target, "cwd": cwd})
    rid, nxt, out = r["id"], 0, []
    end = time.time() + limit
    while time.time() < end:
        p = api(port, f"/api/poll?id={rid}&from={nxt}")
        nxt = p["next"]
        out += p["lines"]
        if p["status"] != "running":
            return "\n".join(out), p["status"], r["cmdline"]
        time.sleep(0.4)
    api(port, "/api/stop", {"id": rid})
    return "\n".join(out), "timeout", r["cmdline"]


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("curl 打靶页")
def t_curl(p, tgt, cwd):
    out, st, cmd = run_tool(p, "curl", [f"{tgt}/?id=1", "", "", "", "", "", "1", "1", "1", "1"], "", "", cwd, 60)
    assert st == "done", f"状态 {st}"
    assert "flag{local_demo_only}" in out, "响应里没有数据"
    return cmd


@case("whatweb 指纹")
def t_whatweb(p, tgt, cwd):
    out, st, cmd = run_tool(p, "whatweb", [f"{tgt}/", "", "", "1"], "", "", cwd, 90)
    assert st == "done", f"状态 {st}"
    assert "PHP" in out.upper(), out[-300:]
    return cmd


@case("ffuf 目录爆破")
def t_ffuf(p, tgt, cwd):
    out, st, cmd = run_tool(p, "ffuf", [f"{tgt}/FUZZ", "wordlists/common.txt", "", "", "", "",
                                       "", "200,301,302,403", "php", "40", "", "1"], "", "", cwd, 180)
    assert st == "done", f"状态 {st}"
    assert "admin" in out.lower(), out[-400:]
    return cmd


@case("sqlmap 注入取证")
def t_sqlmap(p, tgt, cwd):
    out, st, cmd = run_tool(p, "sqlmap", [f"{tgt}/?id=1", "", "", "", "", "sqlite", "1", "1", "", "", "4",
                                          "", "1", "1"], "--tables --flush-session", "", cwd, 240)
    assert st in ("done", "failed"), f"状态 {st}"
    assert "users" in out and "boolean-based blind" in out, out[-500:]
    return cmd


@case("phpggc 列链")
def t_phpggc(p, tgt, cwd):
    out, st, cmd = run_tool(p, "phpggc", ["1", "", "", "", "", "", ""], "", "", cwd, 90)
    assert st == "done", f"状态 {st}"
    assert "Laravel" in out, out[-300:]
    return cmd


@case("shell 自由命令")
def t_shell(p, tgt, cwd):
    out, st, cmd = run_tool(p, "shell", [f"curl -s -o /dev/null -w '%{{http_code}}' {tgt}/"], "", "", cwd, 60)
    assert st == "done" and "200" in out, out[-300:]
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0, help="已在跑的 toolkit 端口；不填则自己起一个")
    ap.add_argument("--keep", action="store_true", help="跑完不关靶站/toolkit")
    a = ap.parse_args()

    procs = []
    tp = a.port
    if not tp:
        tp = 8788
        if not free(tp):
            print(f"端口 {tp} 被占用，用 --port 指定已有实例")
            return 2
        procs.append(subprocess.Popen([sys.executable, str(ROOT / "toolkit.py"), "--no-browser", "--port", str(tp)],
                                      cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        if not wait_port(tp):
            print("toolkit 没起来")
            return 2

    wp = 8899
    if free(wp):
        procs.append(subprocess.Popen(["php", "-S", f"127.0.0.1:{wp}", "-t", str(WEB)],
                                      cwd=WEB, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT))
        if not wait_port(wp):
            print("靶站没起来（php -S 失败？）")
            return 2
    tgt = f"http://127.0.0.1:{wp}"
    cwd = str(ROOT)

    ok = 0
    print(f"toolkit :{tp}   靶站 {tgt}\n" + "─" * 70)
    for name, fn in CASES:
        t0 = time.time()
        try:
            cmd = fn(tp, tgt, cwd)
            ok += 1
            print(f"  ✓ {name:<16} {time.time()-t0:5.1f}s  {cmd[:96]}")
        except AssertionError as e:
            print(f"  ✗ {name:<16} {time.time()-t0:5.1f}s  {e}")
    print("─" * 70)
    print(f"{ok}/{len(CASES)} 通过")

    if not a.keep:
        for p_ in procs:
            p_.terminate()
        for p_ in procs:
            try:
                p_.wait(5)
            except subprocess.TimeoutExpired:
                p_.kill()
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
