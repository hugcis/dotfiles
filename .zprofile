# The following lines were added by Docker Desktop to add commands to your PATH.
export PATH="$PATH:/Users/hugo/.docker/bin"
# End of Docker Desktop section.

# pip zsh completion start
function _pip_completion {
  local words cword
  read -Ac words
  read -cn cword
  reply=( $( COMP_WORDS="$words[*]" \
             COMP_CWORD=$(( cword-1 )) \
             PIP_AUTO_COMPLETE=1 $words[1] 2>/dev/null ))
}
compctl -K _pip_completion pip
# pip zsh completion end

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"

# Re-assert user PATH priority. macOS path_helper runs via /etc/zprofile
# AFTER .zshenv and rebuilds PATH with system dirs first, which demoted
# these entries below /usr/bin (Apple git shadowed the nix-managed git).
typeset -U path
path=(
  "$HOME/.local/bin"
  "$HOME/.local/state/nix/profiles/home-manager/home-path/bin"
  $path
)
export PATH
