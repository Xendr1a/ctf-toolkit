# 提示符、补全、插件只在真的有终端时加载。工具用管道跑 `zsh -i -c` 时没有控制终端，
# job control 开不起来：powerlevel10k 的 gitstatus 在 `setopt monitor` 处失败，
# 先打印 can't change option: monitor，再打印 gitstatus failed to initialize，
# 这些噪声会盖在命令自己的输出前面，看起来像命令出错。
typeset -gi __have_tty=0
[[ -o interactive && -t 0 && -t 1 ]] && __have_tty=1

# 环境变量对所有 shell 生效，包括没有终端的工具调用
# PATH 幂等：交互式 shell 里再起 zsh 时不要重复叠加同一目录
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
export EDITOR="nvim"
export VISUAL="nvim"

# Dragon Mist：ls 配色（24-bit），只给目录/链接/可执行/压缩包/媒体上色
export LS_COLORS='rs=0:fi=38;2;197;201;197:di=38;2;159;185;197:ln=38;2;162;185;183:pi=38;2;207;189;149:so=38;2;184;168;186:do=38;2;184;168;186:bd=38;2;207;189;149:cd=38;2;207;189;149:or=38;2;205;135;129:mi=38;2;205;135;129:su=38;2;205;135;129:sg=38;2;205;135;129:ca=38;2;205;135;129:tw=38;2;157;182;154:ow=38;2;159;185;197:st=38;2;159;185;197:ex=38;2;157;182;154:*.tar=38;2;207;189;149:*.tgz=38;2;207;189;149:*.zip=38;2;207;189;149:*.7z=38;2;207;189;149:*.rar=38;2;207;189;149:*.gz=38;2;207;189;149:*.xz=38;2;207;189;149:*.zst=38;2;207;189;149:*.deb=38;2;207;189;149:*.rpm=38;2;207;189;149:*.jar=38;2;207;189;149:*.png=38;2;184;168;186:*.jpg=38;2;184;168;186:*.jpeg=38;2;184;168;186:*.gif=38;2;184;168;186:*.webp=38;2;184;168;186:*.svg=38;2;184;168;186:*.mp3=38;2;184;168;186:*.flac=38;2;184;168;186:*.wav=38;2;184;168;186:*.ogg=38;2;184;168;186:*.mp4=38;2;184;168;186:*.mkv=38;2;184;168;186:*.webm=38;2;184;168;186:*.mov=38;2;184;168;186:*.pdf=38;2;198;160;138'

# fzf：低对比配色，bg 用终端默认底色
export FZF_DEFAULT_OPTS='--color=fg:#c5c9c5,fg+:#d7dbd5,bg:-1,bg+:#2c2a27,hl:#cfbd95,hl+:#ddcda6,info:#9aa19a,prompt:#9fb9c5,pointer:#9fb9c5,marker:#9db69a,spinner:#9fb9c5,header:#9aa19a,border:#3a3834'

# 与 environment.d/qt-theme.conf 一致；覆盖旧会话继承的 qt5ct。
export QT_QPA_PLATFORMTHEME=qt6ct

# Clash Verge 代理
export http_proxy=http://127.0.0.1:7897
export https_proxy=http://127.0.0.1:7897
export all_proxy=socks5://127.0.0.1:7897
# 本地开发服务直连；保留已有例外。
typeset -aU __proxy_bypass
__proxy_bypass=(localhost 127.0.0.1 ::1 "${(@s:,:)no_proxy}" "${(@s:,:)NO_PROXY}")
export no_proxy="${(j:,:)__proxy_bypass:#}"
export NO_PROXY="$no_proxy"
unset __proxy_bypass

# 登录进 tmux 由 alacritty 的 [terminal.shell] 负责（见 ~/.config/alacritty/alacritty.toml），
# 这里不再 attach：p10k instant prompt 会接管 stdin，放在 zshrc 里必报
# "open terminal failed: not a terminal"。

if (( __have_tty )); then
    # Enable Powerlevel10k instant prompt
    if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
      source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
    fi

    # Oh My Zsh
    export ZSH="/usr/share/oh-my-zsh"
    ZSH_CUSTOM="$HOME/.oh-my-zsh/custom"

    # Theme
    ZSH_THEME="powerlevel10k/powerlevel10k"

    # Plugins
    plugins=(
        git
        z
        zsh-autosuggestions
        zsh-syntax-highlighting
    )

    # Dragon Mist：自动建议与语法高亮保持同一套低对比色
    ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#7a817b'
    typeset -gA ZSH_HIGHLIGHT_STYLES
    ZSH_HIGHLIGHT_STYLES[command]='fg=#9fb9c5'
    ZSH_HIGHLIGHT_STYLES[builtin]='fg=#9fb9c5'
    ZSH_HIGHLIGHT_STYLES[alias]='fg=#9db69a'
    ZSH_HIGHLIGHT_STYLES[function]='fg=#9db69a'
    ZSH_HIGHLIGHT_STYLES[hashed-command]='fg=#9db69a'
    ZSH_HIGHLIGHT_STYLES[path]='fg=#c5c9c5'
    ZSH_HIGHLIGHT_STYLES[globbing]='fg=#cfbd95'
    ZSH_HIGHLIGHT_STYLES[history-expansion]='fg=#cfbd95'
    ZSH_HIGHLIGHT_STYLES[comment]='fg=#7a817b'
    ZSH_HIGHLIGHT_STYLES[single-quoted-argument]='fg=#9db69a'
    ZSH_HIGHLIGHT_STYLES[double-quoted-argument]='fg=#9db69a'
    ZSH_HIGHLIGHT_STYLES[dollar-quoted-argument]='fg=#9db69a'
    ZSH_HIGHLIGHT_STYLES[redirection]='fg=#b8a8ba'
    ZSH_HIGHLIGHT_STYLES[assign]='fg=#9ca6bb'
    ZSH_HIGHLIGHT_STYLES[precommand]='fg=#b8a8ba'
    ZSH_HIGHLIGHT_STYLES[commandseparator]='fg=#9aa19a'
    ZSH_HIGHLIGHT_STYLES[unknown-token]='fg=#cd8781'

    source $ZSH/oh-my-zsh.sh

    # User aliases
    alias vim="nvim"
    alias vi="nvim"
    alias ls="ls --color=auto"
    alias ll="ls -la"
    alias la="ls -A"

    # fzf：Ctrl+R 历史、Ctrl+T 文件、Alt+C 跳目录、**<Tab> 补全
    if command -v fzf >/dev/null 2>&1; then
        source <(fzf --zsh)
    fi

    # p10k 配置
    [[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

    # 可选工具：未安装时不影响 shell 启动。
    if command -v thefuck >/dev/null 2>&1; then
        eval "$(thefuck --alias)"
    fi

    # Oh-my-pi（本机未装则跳过）
    if command -v omp >/dev/null 2>&1; then
        eval "$(omp completions zsh)"
    fi
fi
