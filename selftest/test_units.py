#!/usr/bin/env python3
"""命令拼装、目标替换、字典路径、run 淘汰与桌面后端握手测试。

  python3 -m unittest discover -s selftest -t .   （在仓库根目录）
"""
from __future__ import annotations

import importlib.util
import http.client
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("tk", ROOT / "toolkit.py")
tk = importlib.util.module_from_spec(spec)
sys.modules["tk"] = tk
spec.loader.exec_module(tk)


def _start_backend():
    """起后端（--port 0），从 stdout 读真实端口。失败时抛 RuntimeError。"""
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "toolkit.py"), "--no-browser", "--port", "0"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    ready, _, _ = select.select([proc.stdout], [], [], 3)
    if not ready:
        _stop_backend(proc)
        raise RuntimeError("后端启动超时")
    line = proc.stdout.readline()
    match = re.search(r"http://127\.0\.0\.1:(\d+)/", line)
    if not match:
        _stop_backend(proc)
        raise RuntimeError(f"启动输出缺少 URL: {line!r}")
    return proc, int(match.group(1))


def _stop_backend(proc):
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    proc.stdout.close()
    proc.stderr.close()


def tool(fields, cmd=("echo",), mode="argv"):
    return {"id": "t", "name": "t", "cmd": list(cmd), "mode": mode, "fields": fields}


class BuildTest(unittest.TestCase):
    def test_flags_in_order_and_empty_skipped(self):
        t = tool([
            {"flag": "-a", "kind": "text"},
            {"flag": "-b", "kind": "text"},
            {"flag": "-c", "kind": "bool"},
        ])
        argv, pretty = tk.build(t, ["1", "", "1"], "", "")
        self.assertEqual(argv, ["echo", "-a", "1", "-c"])

    def test_positional_before_flags(self):
        t = tool([
            {"flag": "", "kind": "select"},
            {"flag": "-u", "kind": "text"},
        ])
        argv, _ = tk.build(t, ["dir", "http://x"], "", "")
        self.assertEqual(argv, ["echo", "dir", "-u", "http://x"])

    def test_repeat_splits_lines(self):
        t = tool([{"flag": "-H", "kind": "textarea", "repeat": True}])
        argv, _ = tk.build(t, ["A: 1\nB: 2\n\n"], "", "")
        self.assertEqual(argv, ["echo", "-H", "A: 1", "-H", "B: 2"])

    def test_target_substitution(self):
        t = tool([{"flag": "-u", "kind": "text"}])
        argv, _ = tk.build(t, ["{{TARGET}}/login"], "", "http://h:8080")
        self.assertEqual(argv[-1], "http://h:8080/login")

    def test_target_autofill_placeholder(self):
        t = tool([{"flag": "-u", "kind": "text", "tgt": True, "ph": "{{TARGET}}/FUZZ"}])
        argv, _ = tk.build(t, [""], "", "http://h")
        self.assertEqual(argv[-1], "http://h/FUZZ")

    def test_target_autofill_hostname(self):
        t = tool([{"flag": "", "kind": "text", "tgt": True, "ph": "10.0.0.5"}])
        argv, _ = tk.build(t, [""], "", "http://h:8080/x")
        self.assertEqual(argv[-1], "h")

    def test_user_value_beats_autofill(self):
        t = tool([{"flag": "-u", "kind": "text", "tgt": True, "ph": "{{TARGET}}"}])
        argv, _ = tk.build(t, ["http://mine"], "", "http://other")
        self.assertEqual(argv[-1], "http://mine")

    def test_shell_mode_keeps_pipes(self):
        t = tool([{"flag": "", "kind": "textarea", "raw": True}], cmd=("bash", "-lc"), mode="shell")
        argv, _ = tk.build(t, ["curl -s http://x | head"], "", "")
        self.assertEqual(argv, ["bash", "-lc", "curl -s http://x | head"])

    def test_shell_mode_quotes_non_raw(self):
        t = tool([{"flag": "", "kind": "text"}], cmd=("bash", "-lc"), mode="shell")
        argv, _ = tk.build(t, ["a b; rm -rf /"], "", "")
        self.assertEqual(argv[2], "'a b; rm -rf /'")

    def test_wordlist_path_becomes_absolute(self):
        t = tool([{"flag": "-w", "kind": "text"}])
        argv, pretty = tk.build(t, ["wordlists/common.txt"], "", "")
        self.assertEqual(argv[-1], str(ROOT / "wordlists" / "common.txt"))
        self.assertIn(str(ROOT / "wordlists"), pretty)
        self.assertNotIn(" -w 'wordlists", pretty)      # 不能还是相对路径

    def test_extra_args_shlex_split(self):
        t = tool([{"flag": "-u", "kind": "text"}])
        argv, _ = tk.build(t, ["http://x"], "--batch -D 'my db'", "")
        self.assertEqual(argv, ["echo", "-u", "http://x", "--batch", "-D", "my db"])


class TgtValueTest(unittest.TestCase):
    def test_ph_with_placeholder(self):
        self.assertEqual(tk.tgt_value({"ph": "{{TARGET}}/FUZZ"}, "http://a:1"), "http://a:1/FUZZ")

    def test_ph_without_placeholder_takes_host(self):
        self.assertEqual(tk.tgt_value({"ph": "1.2.3.4"}, "https://host.tld:8443/x?y=1"), "host.tld")

    def test_missing_ph_uses_target(self):
        self.assertEqual(tk.tgt_value({}, "http://a"), "http://a")


class RunEvictionTest(unittest.TestCase):
    def _fake(self, status="done", started=0):
        r = tk.Run("t", "t", "cmd", ["true"], "/tmp")
        r.status, r.started = status, started
        return r

    def test_trim_keeps_newest_and_never_running(self):
        tk.RUNS.clear()
        old = tk.MAX_RUNS
        tk.MAX_RUNS = 3
        try:
            for i in range(6):
                r = self._fake(started=i)
                tk.RUNS[r.id] = r
            hot = self._fake(status="running", started=-1)
            tk.RUNS[hot.id] = hot
            tk.trim_runs()
            self.assertLessEqual(len(tk.RUNS), 4)             # 3 个 + 正在跑的
            self.assertIn(hot.id, tk.RUNS)                    # 运行中的不能被淘汰
            starts = sorted(r.started for r in tk.RUNS.values())
            self.assertIn(5, starts)                          # 最新的留着
            self.assertNotIn(0, starts)                       # 最老的被丢掉
        finally:
            tk.MAX_RUNS = old
            tk.RUNS.clear()


class ConfigTest(unittest.TestCase):
    def test_registry_loads_and_ids_unique(self):
        cfg = tk.load_config()
        ids = [t["id"] for t in cfg["tool"]]
        self.assertGreaterEqual(len(ids), 19)
        self.assertEqual(len(ids), len(set(ids)), "工具 id 重复了")
        for t in cfg["tool"]:
            if t["view"] == "iframe":          # CyberChef 这类只嵌页面，没有命令
                continue
            self.assertTrue(t["cmd"], f"{t['id']} 没有 cmd")
            self.assertTrue(t["category"] in tk.CATEGORIES, f"{t['id']} 分类未知")
            tgt = [f for f in t["fields"] if f.get("tgt")]
            self.assertLessEqual(len(tgt), 1, f"{t['id']} 标了多个 tgt 字段")


class DesktopBackendTest(unittest.TestCase):
    def test_dynamic_port_handshake_and_sigterm(self):
        proc, port = _start_backend()
        try:
            self.assertNotEqual(port, 0)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=2) as response:
                state = json.load(response)
            self.assertIn("tools", state)
        finally:
            _stop_backend(proc)
        self.assertEqual(proc.returncode, 0)


class StaticPathTest(unittest.TestCase):
    def test_static_blocks_symlink_escape(self):
        """web/ 里的符号链接指向仓库外文件，必须返回 403 而不是把内容吐出去。"""
        outside = Path(tempfile.mkdtemp(prefix="tk_outside_"))
        secret = "TOOLKIT_TEST_SECRET_MARKER"
        (outside / "secret.txt").write_text(secret, encoding="utf-8")
        link = ROOT / "web" / f"link_{time.time_ns()}.txt"
        link.symlink_to(outside / "secret.txt")
        proc = None
        try:
            proc, port = _start_backend()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", "/web/" + link.name)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", "replace")
            conn.close()
            self.assertEqual(resp.status, 403, f"符号链接逃逸应被拒，实际 {resp.status}")
            self.assertNotIn(secret, body)
        finally:
            if proc is not None:
                _stop_backend(proc)
            link.unlink(missing_ok=True)
            shutil.rmtree(outside, ignore_errors=True)

    def test_static_blocks_prefix_sibling(self):
        """同级的「前缀混淆」目录（名字是 ROOT 名字加后缀）不能被 startswith 误放行。"""
        h = tk.Handler.__new__(tk.Handler)
        h.command = "GET"
        calls = {}
        h.j = lambda obj, code=200: calls.setdefault("code", code)
        h._send = lambda *a, **k: calls.setdefault("send", True)
        evil = f"{Path(ROOT).name}_evil/secret.txt"
        h.static(Path(ROOT) / "web/../../" / evil, ROOT)
        self.assertEqual(calls.get("code"), 403, "前缀混淆路径应返回 403")


class ApiValidationTest(unittest.TestCase):
    def _handler(self, path):
        """不经过 socket 的 Handler：记录 j()/_send() 的结果。"""
        h = tk.Handler.__new__(tk.Handler)
        h.command = "GET"
        h.path = path
        got = {}
        h.j = lambda obj, code=200: got.update(obj=obj, code=code)
        h._send = lambda code, body, ctype, extra=None: got.update(code=code, body=body)
        return h, got

    def test_poll_rejects_non_numeric_from(self):
        r = tk.Run("t", "t", "cmd", ["true"], "/tmp")
        tk.RUNS[r.id] = r
        try:
            h, got = self._handler(f"/api/poll?id={r.id}&from=abc")
            h.do_GET()
            self.assertEqual(got.get("code"), 400, "非法 from 应返回 400 而不是断连")
        finally:
            tk.RUNS.pop(r.id, None)

    def test_replay_rejects_path_traversal(self):
        d = Path(tempfile.mkdtemp(prefix="tk_rid_"))
        secret = d / "secret.log"
        secret.write_text("TRAVERSAL_MARKER", encoding="utf-8")
        try:
            rid = os.path.relpath(secret, tk.LOGS)[:-len(".log")]
            h, got = self._handler("/api/replay?id=" + urllib.parse.quote(rid))
            h.do_GET()
            self.assertEqual(got.get("code"), 400, "穿越 id 必须被白名单拒绝")
            self.assertNotIn("TRAVERSAL_MARKER", str(got.get("obj")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_replay_accepts_valid_id(self):
        d = Path(tempfile.mkdtemp(prefix="tk_valid_"))
        old = tk.LOGS
        tk.LOGS = d
        (d / "0123456789ab.log").write_text("OK_LINE", encoding="utf-8")
        try:
            h, got = self._handler("/api/replay?id=0123456789ab")
            h.do_GET()
            self.assertEqual(got.get("code"), 200, "合法 12 位 hex id 必须仍可回放")
            self.assertEqual(got.get("obj", {}).get("lines"), ["OK_LINE"])
        finally:
            tk.LOGS = old
            shutil.rmtree(d, ignore_errors=True)

    def test_static_route_confined_to_web(self):
        h, got = self._handler("/web/../tools.toml")
        h.do_GET()
        self.assertEqual(got.get("code"), 403, "静态路由不能逃出 web/")
        h, got = self._handler("/web/style.css")
        h.do_GET()
        self.assertEqual(got.get("code"), 200, "正常静态资源仍要能取到")

    def test_static_blocks_symlinked_index(self):
        """目录请求追加 index.html 后仍要落在 base 内：符号链接 index 不能逃逸。"""
        outside = Path(tempfile.mkdtemp(prefix="tk_idx_outside_"))
        (outside / "index.html").write_text("SYMLINK_INDEX_MARKER", encoding="utf-8")
        sub = ROOT / "web" / f".audit_index_{time.time_ns()}"
        sub.mkdir()
        (sub / "index.html").symlink_to(outside / "index.html")
        try:
            h, got = self._handler("/web/" + sub.name + "/")
            h.do_GET()
            self.assertEqual(got.get("code"), 403, "目录 index 符号链接逃逸应被拒")
            self.assertNotIn(b"SYMLINK_INDEX_MARKER", got.get("body") or b"")
        finally:
            shutil.rmtree(sub, ignore_errors=True)
            shutil.rmtree(outside, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
