# 所有 zsh 进程（含 zsh -c 工具调用）都会读这里；只放导出，别放交互初始化。

# ~/.local/bin 必须排在系统目录前：java/javac 等 wrapper 都在这。
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
# Java 17（与 wrapper 同一套 JDK）；系统 27：env JAVA_HOME=/usr/lib/jvm/default <命令>
export JAVA_HOME="$HOME/opt/jdk/jdk-17.0.21+9"
