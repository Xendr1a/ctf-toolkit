#!/usr/bin/env python3
"""{{NAME}} —— Web 骨架。替换成真实考点；FLAG 只从环境变量读。"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PORT = {{PORT}}

INDEX = b"""<!doctype html>
<meta charset="utf-8">
<title>{{NAME}}</title>
<h1>{{NAME}}</h1>
<p>Web 题目骨架。出题人替换 src/app.py 里的逻辑。</p>
"""


def flag_value() -> str:
    return os.environ.get("GZCTF_FLAG") or os.environ.get("FLAG") or "flag{unset}"


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
        if url.path == "/flag":
            # 演示用的最小校验：真实题目换成自己的判断逻辑。
            if parse_qs(url.query).get("debug") == ["1"]:
                return self._send(200, (flag_value() + "\n").encode(),
                                  "text/plain; charset=utf-8")
            return self._send(403, b"forbidden\n", "text/plain; charset=utf-8")
        return self._send(404, b"not found\n", "text/plain; charset=utf-8")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
