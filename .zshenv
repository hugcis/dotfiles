export PATH="$HOME/.cargo/bin:$PATH"

export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

export VISUAL=vim
export EDITOR="$VISUAL"
export BAT_PAGER="less -R"
export DEFAULT_USER="hugo"

case "$OSTYPE" in
  darwin*)  source ~/.zshenv.macos ;;
  linux*)   source ~/.zshenv.linux ;;
esac

