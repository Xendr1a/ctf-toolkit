# Dragon Mist 本机配置（`local/dotfiles` 分支）

本目录收录 **这台机器**（Arch + niri + Noctalia，用户 Xendr1a）实际在用的桌面配置，以及 Dragon Mist 配色主题。
只放确实改过的文件；与上游（[Mel-SRK/My_config](https://github.com/Mel-SRK/My_config)）相同的文件不在这里，避免两份真相。

分支用途：本机留档、换机/重装时装回去。**不并入 `main`，不 rebase 上游，不 force。**

## 文件对照

| 仓库内路径 | 本机路径 | 来源 | 相对上游的变化 |
|---|---|---|---|
| `dotfiles/niri/config.kdl` | `~/.config/niri/config.kdl` | 本机改写 | `include "outputs.kdl"`、不跑 `swaybg`、键位浮层用中文、Manggo 窗口规则（301 行差异） |
| `dotfiles/niri/outputs.kdl` | `~/.config/niri/outputs.kdl` | Noctalia 插件 `xendr1a/niri-displays` 生成 | 当前 eDP-1 2560x1600@240 scale 1.5、HDMI-A-1 1920x1080@240 scale 1；**不要手改** |
| `dotfiles/alacritty/alacritty.toml` | `~/.config/alacritty/alacritty.toml` | 本机 | import Dragon Mist 主题、`[terminal.shell]` 起 tmux（23 行差异） |
| `dotfiles/alacritty/themes/dragon-mist.toml` | `~/.config/alacritty/themes/dragon-mist.toml` | Dragon Mist 原始定义 | 上游没有此文件；调色板唯一来源 |
| `dotfiles/foot/foot.ini` | `~/.config/foot/foot.ini` | 本机 | include `themes/dragon-mist`、CaskaydiaCove 11pt、padding 14、92% 不透明 + 模糊（9 行差异） |
| `dotfiles/foot/themes/dragon-mist` | `~/.config/foot/themes/dragon-mist` | 由 alacritty 主题派生 | 上游没有此文件；16 色 + 选择/光标 |
| `dotfiles/tmux/.tmux.conf.local` | `~/.config/tmux/.tmux.conf.local` | 本机 | 状态栏与配色（482 行差异），主题上游的 `.tmux.conf` 未改 |
| `dotfiles/zsh/.zshrc` | `~/.zshrc` | 本机 | p10k instant prompt、不 `exec tmux`、别名与本地 PATH（99 行差异） |
| `dotfiles/zsh/.p10k.zsh` | `~/.p10k.zsh` | 上游 p10k 配置 + Dragon Mist 配色 | 92 处 256 色号换成调色板 hex（374 行差异，其中约 186 行是颜色行） |
| `dotfiles/noctalia/settings.toml` | `~/.local/state/noctalia/settings.toml` | Noctalia 实际加载的生效版 | 上游没有此文件；`[bar.default] start` 末尾挂 `xendr1a/lyrics:bar`，`[plugins] enabled` 含 `xendr1a/lyrics` 与 `xendr1a/niri-displays`。与 `.config` 那份有 126 行不同 |

未收录（与上游相同或本机未启用）：`niri/noctalia.kdl`、`tmux/.tmux.conf`、`kanshi/config`（本机没启用 kanshi）、`home/` 下的其他点文件。

## 怎么装回去

默认 **copy**；只有"只读、不会被程序重写、且路径被别的配置引用"的文件才考虑 symlink。
装之前先备份目标：

```bash
backup() { cp -a "$1" "$1.bak-$(date +%F-%H%M)"; }

cd <repo>/dotfiles
backup ~/.config/niri/config.kdl
install -m 644 niri/config.kdl               ~/.config/niri/config.kdl
install -m 644 alacritty/alacritty.toml      ~/.config/alacritty/alacritty.toml
install -m 644 alacritty/themes/dragon-mist.toml ~/.config/alacritty/themes/dragon-mist.toml
install -m 644 foot/foot.ini                 ~/.config/foot/foot.ini
install -m 644 foot/themes/dragon-mist       ~/.config/foot/themes/dragon-mist
install -m 644 tmux/.tmux.conf.local         ~/.config/tmux/.tmux.conf.local
install -m 644 zsh/.zshrc                    ~/.zshrc
install -m 644 zsh/.p10k.zsh                 ~/.p10k.zsh
install -m 644 noctalia/settings.toml        ~/.local/state/noctalia/settings.toml
```

- `niri/config.kdl` 装完先校验：`niri validate -c ~/.config/niri/config.kdl`；niri 会热重载。
- `niri/outputs.kdl` **不用装**：插件每次改布局都会自己写。要装也别用 symlink——插件用 rename 替换文件，symlink 会被换成普通文件。
- `zsh/.p10k.zsh` 不要 symlink：跑一次 `p10k configure` 会整份重写。
- 适合 symlink 的只有两个主题文件（只读）：

  ```bash
  ln -sf "$PWD/alacritty/themes/dragon-mist.toml" ~/.config/alacritty/themes/dragon-mist.toml
  ln -sf "$PWD/foot/themes/dragon-mist"           ~/.config/foot/themes/dragon-mist
  ```

- 本机没装 kitty；原先的 `~/.config/kitty`（含 dragon-mist 主题）已于 2026-11-27 删除，备份在 `~/.local/state/config-backups/20261127-kitty-dragonmist.tar.gz`。

### Noctalia：生效的是 state 那份

Noctalia 5.6 实际加载 `~/.local/state/noctalia/settings.toml`，它会**覆盖** `~/.config/noctalia/settings.toml` 里的同名键。只改 `.config` 那份不生效——歌词栏能出现就是因为在 state 那份的 `[bar.default] start` 里加了 `"xendr1a/lyrics:bar"`，并在 `[plugins] enabled` 里加了 `"xendr1a/lyrics"`。

因此装回去时两份都要铺：

```bash
backup ~/.local/state/noctalia/settings.toml
backup ~/.config/noctalia/settings.toml
install -m 644 noctalia/settings.toml ~/.local/state/noctalia/settings.toml
install -m 644 noctalia/settings.toml ~/.config/noctalia/settings.toml
```

注意：Noctalia 运行时会整份重写 state 那份（改设置、加组件都会写盘），所以仓库里这份是"已知能工作"的快照，不是实时同步源；装之前先备份目标。仓库版本已脱敏：路径统一写成 `/home/user`，`[location] address` 留空，壁纸与头像用 `wallpaper.png` / `avatar.png` 这类占位文件名；本机真实值仍然在 `~/.local/state/noctalia/settings.toml`。

## Dragon Mist 主题来源

色板以 `dotfiles/alacritty/themes/dragon-mist.toml` 为准（低饱和暖灰，背景 `#262421`，前景 `#c5c9c5`）：

| 角色 | hex |
|---|---|
| 绿（成功 / VCS clean） | `#9db69a` |
| 红（错误 / 冲突） | `#cd8781` |
| 黄（警告 / 修改） | `#cfbd95` |
| 蓝（信息 / 未跟踪） | `#9fb9c5` |
| 青（辅助） | `#a2b9b7` |
| 品红 | `#b8a8ba` |
| 灰（次级 / 弱化） | `#8d948d` / `#7a817b` / `#6f746e` |
| 文字 / 亮文字 | `#c5c9c5` / `#d7dbd5` |

foot 主题由它派生 16 色；p10k 的段颜色按原 256 色的色相归到同族 hex、低饱和按明度归灰，`CRITICAL/ERROR/NOT_WRITABLE/NON_EXISTENT` 强制红，`WARNING/LOW/DISCONNECTED` 强制黄，`*_TEST_FOREGROUND` 强制绿。

## 不做的事

- 不并入 `main`、不 rebase 上游、不 force push。
- 不收录未改动的上游文件，也不放凭据（`.gitignore` 里已有 `auth.json`、`.env`、`.ssh/` 等规则）。
- 不把这里的文件同步回上游仓库。
