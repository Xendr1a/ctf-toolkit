#!/usr/bin/env python3
"""{{NAME}} —— Misc 骨架：算对一个哈希前缀换 flag。"""
import hashlib
import os
import socketserver

PORT = {{PORT}}
WORD = "{{NAME}}"


def flag_value() -> str:
    return os.environ.get("GZCTF_FLAG") or os.environ.get("FLAG") or "flag{unset}"


def answer() -> str:
    return hashlib.sha256(WORD.encode()).hexdigest()[:8]


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(f"sha256({WORD!r}) 的前 8 位十六进制？\n> ".encode())
        self.wfile.flush()
        line = self.rfile.readline(4096).decode("utf-8", "replace").strip()
        if line.lower() == answer():
            self.wfile.write((flag_value() + "\n").encode())
        else:
            self.wfile.write(b"wrong\n")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", PORT), Handler) as srv:
        print(f"listening on {PORT}", flush=True)
        srv.serve_forever()
