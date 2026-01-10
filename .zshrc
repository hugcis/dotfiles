# .zshrc - Interactive shell configuration

# History Configuration - Must be set before instant prompt
HISTFILE="${XDG_STATE_HOME:-$HOME/.local/state}/zsh/history"
HISTSIZE=50000
SAVEHIST=50000
mkdir -p "$(dirname "$HISTFILE")" 2>/dev/null

# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# ============================================================================
# Zsh Options - Modern shell behavior
# ============================================================================

# History Options

setopt EXTENDED_HISTORY          # Write timestamp to history
setopt HIST_EXPIRE_DUPS_FIRST    # Expire duplicate entries first
setopt HIST_IGNORE_DUPS          # Don't record duplicate entries
setopt HIST_IGNORE_SPACE         # Ignore commands starting with space
setopt HIST_VERIFY               # Show before executing from history
setopt SHARE_HISTORY             # Share history between sessions
setopt INC_APPEND_HISTORY        # Append to history immediately

# Directory Navigation
setopt AUTO_CD                   # cd by typing directory name
setopt AUTO_PUSHD                # Push directories onto stack
setopt PUSHD_IGNORE_DUPS         # Don't push duplicates
setopt PUSHD_SILENT              # Don't print directory stack

# Completion
setopt COMPLETE_IN_WORD          # Complete from both ends of word
setopt ALWAYS_TO_END             # Move cursor after completion
setopt AUTO_MENU                 # Show completion menu on tab
setopt AUTO_LIST                 # List choices on ambiguous completion
setopt MENU_COMPLETE             # Insert first match immediately

# Globbing
setopt EXTENDED_GLOB             # Extended globbing syntax
setopt GLOB_DOTS                 # Match dotfiles without explicit dot

# ============================================================================
# Oh-My-Zsh Configuration
# ============================================================================

# Path to your oh-my-zsh installation.
export ZSH="$HOME/.oh-my-zsh"

# Set name of the theme to load --- if set to "random", it will
# load a random theme each time oh-my-zsh is loaded, in which case,
# to know which specific one was loaded, run: echo $RANDOM_THEME
# See https://github.com/robbyrussell/oh-my-zsh/wiki/Themes
ZSH_THEME="powerlevel10k/powerlevel10k"

# Set list of themes to pick from when loading at random
# Setting this variable when ZSH_THEME=random will cause zsh to load
# a theme from this variable instead of looking in ~/.oh-my-zsh/themes/
# If set to an empty array, this variable will have no effect.
# ZSH_THEME_RANDOM_CANDIDATES=( "robbyrussell" "agnoster" )

# Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# Uncomment the following line to use hyphen-insensitive completion.
# Case-sensitive completion must be off. _ and - will be interchangeable.
# HYPHEN_INSENSITIVE="true"

# Uncomment the following line to disable bi-weekly auto-update checks.
# DISABLE_AUTO_UPDATE="true"

# Uncomment the following line to change how often to auto-update (in days).
# export UPDATE_ZSH_DAYS=13

# Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# Uncomment the following line to enable command auto-correction.
# ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
# COMPLETION_WAITING_DOTS="true"

# Uncomment the following line if you want to disable marking untracked files
# under VCS as dirty. This makes repository status check for large repositories
# much, much faster.
DISABLE_UNTRACKED_FILES_DIRTY="true"

# Uncomment the following line if you want to change the command execution time
# stamp shown in the history command output.
# You can set one of the optional three formats:
# "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# or set a custom format using the strftime function format specifications,
# see 'man strftime' for details.
# HIST_STAMPS="mm/dd/yyyy"

# Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# Which plugins would you like to load?
# Standard plugins can be found in ~/.oh-my-zsh/plugins/*
# Custom plugins may be added to ~/.oh-my-zsh/custom/plugins/
# Example format: plugins=(rails git textmate ruby lighthouse)
# Add wisely, as too many plugins slow down shell startup.

plugins=(
  git
  brew
  poetry
  z
  shrink-path
  zsh-autosuggestions
  zsh-syntax-highlighting
)

HOST=$(hostname)

source $ZSH/oh-my-zsh.sh

# ============================================================================
# User Configuration
# ============================================================================

# Key Bindings - Emacs-style by default, uncomment for vi-mode
# bindkey -v
bindkey '^[[A' history-substring-search-up      # Up arrow
bindkey '^[[B' history-substring-search-down    # Down arrow
bindkey '^[[Z' reverse-menu-complete            # Shift+Tab
bindkey '^[[3~' delete-char                     # Delete key

# ============================================================================
# Aliases
# ============================================================================

# Directory listing (using lsd if available, falls back to ls)
if command -v lsd &> /dev/null; then
  alias ls='lsd -F'
  alias ll='lsd -lF'
  alias la='lsd -aF'
  alias lla='lsd -laF'
  alias tree='lsd --tree'
else
  alias la='ls -a'
  alias ll='ls -lh'
fi

# Quick directory size
alias ssize="find -X . -depth 1 | xargs du -hs | sort -h"

# Utilities
alias rot13="tr 'A-Za-z' 'N-ZA-Mn-za-m'"
alias config='git --git-dir=$HOME/.cfg/ --work-tree=$HOME'

# Better defaults
alias grep='grep --color=auto'
alias df='df -h'
alias du='du -h'
alias free='free -h'

# Quick navigation
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'

# ============================================================================
# Development Tools - Lazy Loading for Performance
# ============================================================================

# NVM (Node Version Manager) - Lazy load for faster shell startup
export NVM_DIR="$HOME/.nvm"
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
  # Lazy load NVM
  nvm() {
    unset -f nvm node npm
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
    nvm "$@"
  }

  node() {
    unset -f nvm node npm
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
    node "$@"
  }

  npm() {
    unset -f nvm node npm
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
    npm "$@"
  }
fi

# ============================================================================
# Integrations
# ============================================================================

# Powerlevel10k theme customization
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

# FZF fuzzy finder
[[ -f ~/.fzf.zsh ]] && source ~/.fzf.zsh

# Z jump tool (fallback if oh-my-zsh plugin doesn't work)
[[ -f ~/z.sh ]] || [[ -f ~/.local/share/z/z.sh ]] && source ~/.local/share/z/z.sh

# ============================================================================
# OS-Specific Configuration
# ============================================================================

case "$OSTYPE" in
  darwin*)  [[ -f ~/.zshrc.macos ]] && source ~/.zshrc.macos ;;
  linux*)   [[ -f ~/.zshrc.linux ]] && source ~/.zshrc.linux ;;
esac
