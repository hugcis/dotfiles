# .zshenv - Environment variables for all shells (interactive and non-interactive)
# Keep this minimal for fast shell startup

# Locale settings
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

# Default editor
export VISUAL=vim
export EDITOR="$VISUAL"

# Pager settings
export BAT_PAGER="less -R"
export PAGER="less"
export LESS="-R -F -X"

# User info
export DEFAULT_USER="hugo"

# XDG Base Directory specification
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"

# Rust/Cargo - add early for tools that might need it
export PATH="$HOME/.cargo/bin:$PATH"

# Load OS-specific environment
case "$OSTYPE" in
  darwin*)  [[ -f ~/.zshenv.macos ]] && source ~/.zshenv.macos ;;
  linux*)   [[ -f ~/.zshenv.linux ]] && source ~/.zshenv.linux ;;
esac

