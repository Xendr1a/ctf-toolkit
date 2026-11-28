#!/usr/bin/env python3
"""{{NAME}} —— Crypto 骨架：单字节 XOR 密文，提交明文换 flag。"""
import os
import socketserver

PORT = {{PORT}}
KEY = 0x5A


def flag_value() -> str:
    return os.environ.get("GZCTF_FLAG") or os.environ.get("FLAG") or "flag{unset}"


def xor(data: bytes, key: int) -> bytes:
    return bytes(b ^ key for b in data)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        plain = flag_value().encode()
        self.wfile.write(b"cipher(hex) = " + xor(plain, KEY).hex().encode() + b"\n")
        self.wfile.write(b"submit plaintext> ")
        self.wfile.flush()

        line = self.rfile.readline(4096).strip()
        if line == plain:
            self.wfile.write(b"correct\n")
        else:
            self.wfile.write(b"wrong\n")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", PORT), Handler) as srv:
        print(f"listening on {PORT}", flush=True)
        srv.serve_forever()
