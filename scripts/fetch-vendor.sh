#!/usr/bin/env bash
# 拉取体积大的外部资源：离线 CyberChef + SecLists 字典。
# 换机器或 vendor/ 被清掉后跑一次即可（不依赖网络的话可以先不跑，工具页仍可用）。
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

CC_TAG="v11.6.0"
CC_ZIP="CyberChef_f464d62c7c943cda9749a765932a7548ba9bfb16.zip"
SL="https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content"

echo "==> SecLists 字典"
mkdir -p wordlists
for f in raft-small-directories.txt raft-small-words.txt common.txt; do
    [ -s "wordlists/$f" ] && { echo "    已有 $f"; continue; }
    curl -sSL --max-time 120 -o "wordlists/$f" "$SL/$f"
    printf '    %-32s %s 行\n' "$f" "$(wc -l < "wordlists/$f")"
done

echo "==> CyberChef $CC_TAG (~80MB)"
if [ -f vendor/cyberchef/index.html ]; then
    echo "    已有 vendor/cyberchef/index.html"
else
    mkdir -p vendor/cyberchef
    curl -sSL --max-time 900 -o "vendor/$CC_ZIP" \
        "https://github.com/gchq/CyberChef/releases/download/$CC_TAG/$CC_ZIP"
    unzip -o -q "vendor/$CC_ZIP" -d vendor/cyberchef
    # release 里的单页文件名带版本号，统一成 index.html
    for h in vendor/cyberchef/CyberChef_v*.html; do [ -e "$h" ] && mv "$h" vendor/cyberchef/index.html; done
    rm -f vendor/cyberchef/index.html.br vendor/cyberchef/index.html.gz "vendor/$CC_ZIP"
    echo "    解包完成: $(du -sh vendor/cyberchef | cut -f1)"
fi
