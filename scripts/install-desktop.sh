#!/usr/bin/env bash
# install-desktop.sh —— 把 Tauri 桌面壳装成应用菜单入口（fuzzel/rofi 等可见）
# 用法: bash scripts/install-desktop.sh   （先 npx tauri build）
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bin="$root/src-tauri/target/release/ctf-toolkit"
[ -x "$bin" ] || { echo "先构建: npx tauri build"; exit 1; }

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
ln -sf "$bin" "$HOME/.local/bin/ctf-toolkit"

cat > "$HOME/.local/share/applications/ctf-toolkit.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=CTF Toolkit
Comment=本地 CTF Web 工具台（多任务并行）
Exec=$HOME/.local/bin/ctf-toolkit
Icon=$root/src-tauri/icons/128x128.png
Terminal=false
Categories=Security;System;
StartupWMClass=ctf-toolkit
EOF

command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" || true
echo "已安装: $HOME/.local/bin/ctf-toolkit + 应用菜单入口"
