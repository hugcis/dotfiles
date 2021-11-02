export PATH="$HOME/.cargo/bin:$PATH"
export GEOS_DIR=/usr/local/Cellar/geos/3.5.0/

export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

# java development kit
export JDK_HOME=/Library/Java/JavaVirtualMachines/jdk1.8.0_121.jdk/Contents/Home
PATH=$PATH:/opt/metasploit-framework/bin
export PATH=$PATH:/opt/metasploit-framework/bin

# Use macvim
export PATH="/usr/local/Cellar/macvim/8.1-155/bin/vim:$PATH"

# The next line updates PATH for the Google Cloud SDK.
if [ -f '/Users/hugo/google-cloud-sdk/path.zsh.inc' ]; then . '/Users/hugo/google-cloud-sdk/path.zsh.inc'; fi

# The next line enables shell command completion for gcloud.
if [ -f '/Users/hugo/google-cloud-sdk/completion.zsh.inc' ]; then . '/Users/hugo/google-cloud-sdk/completion.zsh.inc'; fi
export TERM=xterm-256color

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

#export PATH="$PATH:$HOME/anaconda3/bin"

export VISUAL=vim
export EDITOR="$VISUAL"
export PATH="/usr/local/bin:$PATH"
export PATH="/Library/TeX/texbin:$PATH"
export BAT_PAGER="less -R"
export DEFAULT_USER="hugo"

export PATH="/usr/local/opt/make/libexec/gnubin:$PATH"

unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)     
eval $(keychain --eval --quiet id_ed25519 id_rsa)
;;
esac

export PATH="$HOME/.poetry/bin:$PATH"
export PATH="$PATH:/Applications/Julia-1.5.app/Contents/Resources/julia/bin/"
export PATH="/usr/local/sbin:$PATH"
export PATH="/Users/hugo/.pyenv/bin:$PATH"
export PATH="/Users/hugo/.local/bin:$PATH"

export OPENBLAS="$(brew --prefix openblas)"
if [ -e /Users/hugo/.nix-profile/etc/profile.d/nix.sh ]; then . /Users/hugo/.nix-profile/etc/profile.d/nix.sh; fi # added by Nix installer
