# Brewfile — declarative macOS package management
# Usage: brew bundle install --file=~/Brewfile --no-lock

# ============================================================================
# Taps
# ============================================================================
tap "d12frosted/emacs-plus"
tap "homebrew/bundle"
tap "tw93/tap"

# ============================================================================
# Core CLI Tools
# ============================================================================
# git, gh, just: now managed by home-manager (~/.config/home-manager/modules/packages.nix)
brew "coreutils"
brew "findutils"
brew "make"
brew "cmake"
brew "ninja"

# ============================================================================
# Shell & Terminal
# ============================================================================
# fzf, ripgrep, fd, bat, lsd, btop, htop, ncdu, tree, pv, tmux, zellij,
# starship: now managed by home-manager
brew "watch"

# ============================================================================
# Text & Spelling
# ============================================================================
brew "aspell"
brew "hunspell"

# ============================================================================
# Git & VCS
# ============================================================================
brew "git-lfs"
# tig: now managed by home-manager

# ============================================================================
# Editors
# ============================================================================
brew "macvim"
brew "d12frosted/emacs-plus/emacs-plus@29", args: ["with-native-comp"]

# ============================================================================
# Languages & Runtimes
# ============================================================================
brew "pyenv"
brew "uv"
brew "node"
brew "gcc"
brew "llvm"
brew "zig"

# ============================================================================
# Networking & Security
# ============================================================================
brew "openssh"
# wget: now managed by home-manager
brew "nmap"
brew "iperf3"
brew "gnupg"
brew "pinentry-mac"
brew "pass"
brew "bcrypt"

# ============================================================================
# Media & Image Processing
# ============================================================================
brew "ffmpeg"
brew "imagemagick"
brew "gifsicle"
brew "dcraw"
brew "typst"

# ============================================================================
# Data & Science
# ============================================================================
brew "hdf5"
brew "gdal"
brew "apache-arrow"

# ============================================================================
# Misc Utilities
# ============================================================================
brew "parallel"
brew "p7zip"
brew "socat"
# tokei: now managed by home-manager
brew "gnu-units"
brew "tw93/tap/mole"

# ============================================================================
# Cask Apps
# ============================================================================
cask "1password-cli"
cask "alacritty"  # .app registration for Spotlight; the nix HM binary wins on PATH in shells
cask "darktable"
cask "font-meslo-lg-nerd-font"
