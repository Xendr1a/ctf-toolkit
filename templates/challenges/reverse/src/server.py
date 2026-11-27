#!/usr/bin/env python3
"""{{NAME}} —— Reverse 骨架：发二进制 + 校验口令换 flag。"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PORT = {{PORT}}
PASSWORD = "{{NAME}}-r3v"
CHALL = Path("/app/chall")

INDEX = b"""<!doctype html>
<meta charset="utf-8">
<title>{{NAME}}</title>
<h1>{{NAME}}</h1>
<p>下载 <a href="/chall">/chall</a>，逆出口令后提交到 <code>/flag?password=...</code>。</p>
"""


def flag_value() -> str:
    return os.environ.get("GZCTF_FLAG") or os.environ.get("FLAG") or "flag{unset}"


def check(password: str) -> bool:
    return password == PASSWORD


class Handler(BaseHTTPRequestHandler):
    server_version = "{{NAME}}"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/":
            return self._send(200, INDEX)
        if url.path == "/chall":
            try:
                data = CHALL.read_bytes()
            except OSError:
                return self._send(500, b"binary missing\n", "text/plain; charset=utf-8")
            return self._send(200, data, "application/octet-stream")
        if url.path == "/flag":
            pw = parse_qs(url.query).get("password", [""])[0]
            if check(pw):
                return self._send(200, (flag_value() + "\n").encode(),
                                  "text/plain; charset=utf-8")
            return self._send(403, b"wrong password\n", "text/plain; charset=utf-8")
        return self._send(404, b"not found\n", "text/plain; charset=utf-8")

    def do_POST(self):
        url = urlsplit(self.path)
        if url.path != "/flag":
            return self._send(404, b"not found\n", "text/plain; charset=utf-8")
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(n, 8192)).decode("utf-8", "replace")
        pw = parse_qs(body).get("password", [""])[0]
        if check(pw):
            return self._send(200, (flag_value() + "\n").encode(),
                              "text/plain; charset=utf-8")
        return self._send(403, b"wrong password\n", "text/plain; charset=utf-8")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
