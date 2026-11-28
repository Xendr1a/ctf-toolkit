#!/usr/bin/env python3
"""题目脚手架：生成可本地起、可上传 GZCTF 的题目工程，并做 compose 冒烟。

  toolkit new-challenge <name> --cat pwn|web|crypto|misc|reverse [--dest DIR]
  toolkit test-challenge <dir> [--timeout 300]

只生成文件 + 调 docker compose；不接 GZCTF API、不存状态、不记分。
模板在 templates/challenges/{common,<cat>}/，用 {{NAME}} 这类占位符渲染。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates" / "challenges"

NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}")
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

# 数据驱动：新增分类只加目录 + 这里一条。
CATEGORIES = {
    "pwn": {
        "title": "Pwn",
        "port": 31337,
        "access": "nc 127.0.0.1 {port}",
        "attachments": [],
        "attach_human": "无（动态容器，直接连服务）",
    },
    "web": {
        "title": "Web",
        "port": 8080,
        "access": "curl -i http://127.0.0.1:{port}/",
        "attachments": [],
        "attach_human": "无（动态容器，直接访问）",
    },
    "crypto": {
        "title": "Crypto",
        "port": 31337,
        "access": "nc 127.0.0.1 {port}",
        "attachments": [],
        "attach_human": "无（动态容器，直接连服务）",
    },
    "misc": {
        "title": "Misc",
        "port": 31337,
        "access": "nc 127.0.0.1 {port}",
        "attachments": [],
        "attach_human": "无（动态容器，直接连服务）",
    },
    "reverse": {
        "title": "Reverse",
        "port": 8080,
        "access": "curl -O http://127.0.0.1:{port}/chall",
        "attachments": ["dist/chall"],
        "attach_human": "`dist/chall`（先在本机跑 `make`）",
    },
}


class CliError(Exception):
    """用户可见错误：只打印消息，不吐 traceback。"""


def _image(name: str) -> str:
    return "ctf-" + name.lower().replace("_", "-") + ":latest"


def _values(name: str, cat: str) -> dict[str, str]:
    info = CATEGORIES[cat]
    desc = f"{name}：{info['title']} 题目骨架（先替换 src/ 里的逻辑，再发布）。"
    attachments = info["attachments"]
    return {
        "NAME": name,
        "NAME_JSON": json.dumps(name, ensure_ascii=False),
        "CATEGORY": cat,
        "CATEGORY_TITLE": info["title"],
        "CATEGORY_TITLE_JSON": json.dumps(info["title"], ensure_ascii=False),
        "PORT": str(info["port"]),
        "IMAGE": _image(name),
        "IMAGE_JSON": json.dumps(_image(name), ensure_ascii=False),
        "CONTENT_JSON": json.dumps(desc, ensure_ascii=False),
        "ATTACHMENTS_JSON": json.dumps(attachments, ensure_ascii=False),
        "ATTACHMENTS_HUMAN": info["attach_human"],
        "ATTACHMENT_NAME_JSON": json.dumps(Path(attachments[0]).name if attachments else "",
                                           ensure_ascii=False),
        "ACCESS_HINT": info["access"].format(port=info["port"]),
    }


def _render(text: str, values: dict[str, str], where: Path) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise CliError(f"{where}: 未知模板占位符 {{{{{key}}}}}")
        return values[key]

    return PLACEHOLDER_RE.sub(repl, text)


def _write_tree(base: Path, dst: Path, values: dict[str, str]) -> list[str]:
    """把模板目录渲染到 dst，返回相对路径清单。所有文件都过一遍占位符。"""
    if not base.is_dir():
        raise CliError(f"模板缺失: {base}")
    created: list[str] = []
    for src in sorted(p for p in base.rglob("*") if p.is_file()):
        rel = src.relative_to(base)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = src.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            shutil.copyfile(src, out)
        else:
            out.write_text(_render(text, values, src), encoding="utf-8")
        shutil.copymode(src, out)
        created.append(str(rel))
    return created


def new_challenge(name: str, cat: str, dest: str | None) -> int:
    if not NAME_RE.fullmatch(name):
        raise CliError("题目名只能用字母/数字/下划线/连字符，字母或数字开头（≤48 字符）")
    if cat not in CATEGORIES:
        raise CliError(f"未知分类: {cat}（可选: {', '.join(CATEGORIES)}）")

    target = Path(dest).expanduser() if dest else Path.cwd() / name
    if not target.is_absolute():
        target = Path.cwd() / target
    target = Path(os.path.abspath(target))
    if target.exists():
        raise CliError(f"目标已存在，不覆盖: {target}")

    parent = target.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=parent))
    except OSError as e:
        raise CliError(f"无法创建目标目录 {parent}: {e}") from e

    values = _values(name, cat)
    try:
        files = _write_tree(TEMPLATES / "common", tmp, values)
        files += _write_tree(TEMPLATES / cat, tmp, values)
        json.loads((tmp / "challenge.json").read_text(encoding="utf-8"))  # 渲染后必须是合法 JSON
        tmp.rename(target)
    except CliError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except (OSError, ValueError) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise CliError(f"生成失败: {e}") from e

    print(f"已生成 {CATEGORIES[cat]['title']} 题目 {name}")
    print(f"  目录: {target}")
    for rel in files:
        print(f"  {rel}")
    print()
    print("下一步:")
    print(f"  cd {target}")
    print("  cp flag.txt.example flag.txt   # 改成真 flag；flag.txt 已被 .gitignore 忽略")
    print("  toolkit test-challenge .")
    return 0


def _compose_prefix() -> list[str] | None:
    """优先 docker compose (v2)，退到 docker-compose (v1)；都没有返回 None。"""
    if shutil.which("docker"):
        try:
            r = subprocess.run(["docker", "compose", "version"],
                               capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            r = None
        if r is not None and r.returncode == 0:
            return ["docker", "compose"]
    exe = shutil.which("docker-compose")
    if exe:
        try:
            r = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            r = None
        if r is not None and r.returncode == 0:
            return [exe]
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_port(port: int, deadline: float) -> bool:
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.25)
    return False


def _expose_port(project: Path) -> int:
    path = project / "challenge.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise CliError(f"读不到 {path}: {e}") from e
    except ValueError as e:
        raise CliError(f"{path} 不是合法 JSON: {e}") from e
    port = data.get("exposePort")
    if port is None and isinstance(data.get("container"), dict):
        port = data["container"].get("exposePort")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise CliError(f"{path} 缺少合法的 exposePort（容器内端口）")
    return port


def _local_flag(project: Path) -> tuple[str, str]:
    """返回 (flag, 来源说明)。flag.txt 优先，其次环境变量 FLAG，最后自测占位。"""
    f = project / "flag.txt"
    if f.is_file():
        val = f.read_text(encoding="utf-8", errors="replace").strip()
        if val:
            return val, "flag.txt"
    val = os.environ.get("FLAG", "").strip()
    if val:
        return val, "环境变量 FLAG"
    return "flag{test_local_only}", "自测占位"


def _project_name(project: Path) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", f"ctf-test-{project.name}-{os.getpid()}".lower())
    return slug[:60].strip("-_") or "ctf-test"


def test_challenge(folder: str, timeout: int) -> int:
    project = Path(folder).expanduser()
    if not project.is_absolute():
        project = Path.cwd() / project
    project = Path(os.path.abspath(project))
    if not project.is_dir():
        raise CliError(f"目录不存在: {project}")
    if not (project / "docker-compose.yml").is_file():
        raise CliError(f"不是题目工程（缺 docker-compose.yml）: {project}")

    port = _expose_port(project)
    prefix = _compose_prefix()
    if prefix is None:
        print("错误: 未找到 Docker Compose。", file=sys.stderr)
        print("  需要 `docker compose`（v2 插件）或 `docker-compose`（v1）其一。", file=sys.stderr)
        print("  Arch: sudo pacman -S docker-compose；其他发行版见 Docker 文档。", file=sys.stderr)
        return 3

    host_port = _free_port()
    flag, flag_src = _local_flag(project)
    env = os.environ.copy()
    env["FLAG"] = flag
    env["HOST_PORT"] = str(host_port)
    project_name = _project_name(project)
    base = prefix + ["-p", project_name, "-f", "docker-compose.yml"]
    deadline = time.time() + max(1, timeout)

    print(f"题目: {project}")
    print(f"compose: {' '.join(prefix)}")
    print(f"容器内端口: {port}  本机映射: {host_port}")
    print(f"FLAG 来源: {flag_src}（内容不打印）")
    print("→ docker compose up -d --build")

    up_rc = 1
    port_ok = False
    teardown_rc = 0
    try:
        try:
            up_rc = subprocess.run(
                base + ["up", "-d", "--build"],
                cwd=str(project), env=env, timeout=max(1.0, deadline - time.time()),
            ).returncode
        except subprocess.TimeoutExpired:
            print(f"错误: compose up 超过 {timeout}s", file=sys.stderr)
            up_rc = 1
        if up_rc != 0:
            print(f"错误: compose up 退出码 {up_rc}", file=sys.stderr)
        else:
            print(f"→ 探活 127.0.0.1:{host_port}（最多等 {timeout}s）")
            port_ok = _wait_port(host_port, deadline)
            if port_ok:
                print(f"✓ 端口 {host_port} 已连通（容器内 {port}）")
            else:
                print(f"错误: {timeout}s 内端口 {host_port} 未连通", file=sys.stderr)
    finally:
        print("→ docker compose down -v --remove-orphans")
        try:
            teardown_rc = subprocess.run(
                base + ["down", "-v", "--remove-orphans"],
                cwd=str(project), env=env, timeout=120,
            ).returncode
        except subprocess.TimeoutExpired:
            print("错误: compose down 超时，请手动清理", file=sys.stderr)
            teardown_rc = 1
        except OSError as e:
            print(f"错误: compose down 失败: {e}", file=sys.stderr)
            teardown_rc = 1

    if teardown_rc != 0:
        print(f"错误: teardown 退出码 {teardown_rc}，可能有残留容器", file=sys.stderr)
        return 1
    if up_rc == 0 and port_ok:
        print("✓ 通过：起得来、端口通（未解题验证）")
        return 0
    return 1


def _new_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="toolkit new-challenge",
        description="生成可本地起、可上传 GZCTF 的题目工程",
    )
    ap.add_argument("name", help="题目名（目录名/镜像名，字母数字_-）")
    ap.add_argument("--cat", required=True, choices=list(CATEGORIES), help="题目分类")
    ap.add_argument("--dest", default=None, help="生成目录（默认 ./<name>）")
    return ap


def _test_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="toolkit test-challenge",
        description="compose up → 探活端口 → 无条件 teardown",
    )
    ap.add_argument("dir", help="题目工程目录（含 docker-compose.yml / challenge.json）")
    ap.add_argument("--timeout", type=int, default=300,
                    help="构建+启动+探活总超时秒数（默认 300）")
    return ap


def cli(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print("用法:\n"
              "  toolkit new-challenge <name> --cat pwn|web|crypto|misc|reverse [--dest DIR]\n"
              "  toolkit test-challenge <dir> [--timeout 300]")
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "new-challenge":
            a = _new_parser().parse_args(rest)
            return new_challenge(a.name, a.cat, a.dest)
        if cmd == "test-challenge":
            a = _test_parser().parse_args(rest)
            return test_challenge(a.dir, a.timeout)
    except CliError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2
    print(f"未知子命令: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
