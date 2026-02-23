#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Dotfiles dependency installer
# Safe to re-run — each section checks if tools are already installed.
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[info]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[skip]${NC}  $*"; }
err()   { echo -e "${RED}[err]${NC}   $*"; }

OS="$(uname -s)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

has() { command -v "$1" &>/dev/null; }

confirm() {
    local prompt="$1"
    read -rp "$(echo -e "${BLUE}[?]${NC}  ${prompt} [Y/n] ")" answer
    [[ -z "$answer" || "$answer" =~ ^[Yy] ]]
}

# ---------------------------------------------------------------------------
# 1. Package manager
# ---------------------------------------------------------------------------

section_package_manager() {
    info "--- Package manager ---"
    if [[ "$OS" == "Darwin" ]]; then
        if has brew; then
            ok "Homebrew already installed"
        else
            info "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    elif [[ "$OS" == "Linux" ]]; then
        if has apt-get; then
            info "Updating apt..."
            sudo apt-get update -qq
        else
            warn "No supported package manager found (expected apt)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 2. CLI tools
# ---------------------------------------------------------------------------

section_cli_tools() {
    info "--- CLI tools ---"
    if [[ "$OS" == "Darwin" ]]; then
        local formulae=(
            git
            gh
            fzf
            lsd
            bat
            tmux
            zellij
            coreutils
            make
            gnu-sed
            cmake       # needed by Doom Emacs vterm
            aspell      # spell checking in Emacs
            ripgrep
        )
        local to_install=()
        for f in "${formulae[@]}"; do
            if brew list --formula "$f" &>/dev/null; then
                ok "$f"
            else
                to_install+=("$f")
            fi
        done
        if [[ ${#to_install[@]} -gt 0 ]]; then
            info "Installing: ${to_install[*]}"
            brew install "${to_install[@]}"
        fi
    elif [[ "$OS" == "Linux" ]]; then
        local packages=(
            git
            gh
            fzf
            tmux
            cmake
            aspell
            ripgrep
            keychain
            xclip
            xsel
        )
        local to_install=()
        for p in "${packages[@]}"; do
            if dpkg -s "$p" &>/dev/null 2>&1; then
                ok "$p"
            else
                to_install+=("$p")
            fi
        done
        if [[ ${#to_install[@]} -gt 0 ]]; then
            info "Installing: ${to_install[*]}"
            sudo apt-get install -y "${to_install[@]}"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 3. Cask apps (macOS only)
# ---------------------------------------------------------------------------

section_cask_apps() {
    [[ "$OS" != "Darwin" ]] && return
    info "--- macOS cask apps ---"
    local casks=(
        alacritty
        font-meslo-lg-nerd-font
    )
    local to_install=()
    for c in "${casks[@]}"; do
        if brew list --cask "$c" &>/dev/null 2>&1; then
            ok "$c"
        else
            to_install+=("$c")
        fi
    done
    if [[ ${#to_install[@]} -gt 0 ]]; then
        info "Installing: ${to_install[*]}"
        brew install --cask "${to_install[@]}"
    fi
}

# ---------------------------------------------------------------------------
# 4. Oh-My-Zsh + theme + plugins
# ---------------------------------------------------------------------------

section_omz() {
    info "--- Oh-My-Zsh ---"

    # oh-my-zsh
    if [[ -d "$HOME/.oh-my-zsh" ]]; then
        ok "oh-my-zsh"
    else
        info "Installing oh-my-zsh..."
        RUNZSH=no sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
    fi

    local omz_custom="$HOME/.oh-my-zsh/custom"

    # Powerlevel10k
    if [[ -d "$omz_custom/themes/powerlevel10k" ]]; then
        ok "powerlevel10k"
    else
        info "Installing powerlevel10k..."
        git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$omz_custom/themes/powerlevel10k"
    fi

    # Custom plugins
    local entries=(
        "zsh-autosuggestions https://github.com/zsh-users/zsh-autosuggestions"
        "zsh-syntax-highlighting https://github.com/zsh-users/zsh-syntax-highlighting"
    )
    local entry name url
    for entry in "${entries[@]}"; do
        name="${entry%% *}"
        url="${entry#* }"
        if [[ -d "$omz_custom/plugins/$name" ]]; then
            ok "$name"
        else
            info "Installing $name..."
            git clone "$url" "$omz_custom/plugins/$name"
        fi
    done
}

# ---------------------------------------------------------------------------
# 5. Rust
# ---------------------------------------------------------------------------

section_rust() {
    info "--- Rust ---"
    if has rustup; then
        ok "rustup"
    else
        info "Installing rustup..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
        source "$HOME/.cargo/env"
    fi
    # Ensure nightly toolchain is available (needed for rust-src / rust-analyzer)
    if rustup toolchain list | grep -q nightly; then
        ok "nightly toolchain"
    else
        info "Installing nightly toolchain..."
        rustup toolchain install nightly
        rustup component add rust-src --toolchain nightly
    fi
}

# ---------------------------------------------------------------------------
# 6. Node.js (NVM)
# ---------------------------------------------------------------------------

section_nvm() {
    info "--- NVM / Node.js ---"
    if [[ -d "$HOME/.nvm" ]]; then
        ok "nvm"
    else
        info "Installing nvm..."
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    fi
    # Install latest LTS if no node version present
    export NVM_DIR="$HOME/.nvm"
    # shellcheck disable=SC1091
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    if has node; then
        ok "node $(node --version)"
    else
        info "Installing latest LTS Node.js..."
        nvm install --lts
    fi
}

# ---------------------------------------------------------------------------
# 7. Python (pyenv)
# ---------------------------------------------------------------------------

section_python() {
    info "--- pyenv / Python ---"
    if has pyenv; then
        ok "pyenv"
    else
        if [[ "$OS" == "Darwin" ]]; then
            info "Installing pyenv via Homebrew..."
            brew install pyenv
        else
            info "Installing pyenv..."
            curl https://pyenv.run | bash
        fi
    fi
    if has poetry; then
        ok "poetry"
    else
        info "Installing poetry..."
        curl -sSL https://install.python-poetry.org | python3 -
    fi
}

# ---------------------------------------------------------------------------
# 8. Doom Emacs
# ---------------------------------------------------------------------------

section_doom() {
    info "--- Doom Emacs ---"

    # Emacs itself
    if has emacs; then
        ok "emacs ($(emacs --version | head -1))"
    else
        if [[ "$OS" == "Darwin" ]]; then
            info "Installing emacs-plus@29 via d12frosted tap..."
            brew tap d12frosted/emacs-plus 2>/dev/null || true
            brew install emacs-plus@29
        else
            info "Installing Emacs..."
            sudo apt-get install -y emacs
        fi
    fi

    # Doom
    if [[ -d "$HOME/.emacs.d" ]] && [[ -f "$HOME/.emacs.d/bin/doom" ]]; then
        ok "doom emacs"
    else
        info "Installing Doom Emacs..."
        git clone --depth 1 https://github.com/doomemacs/doomemacs "$HOME/.emacs.d"
        "$HOME/.emacs.d/bin/doom" install
    fi
}

# ---------------------------------------------------------------------------
# 9. Git submodules (tmux framework)
# ---------------------------------------------------------------------------

section_submodules() {
    info "--- Git submodules ---"
    if [[ -d "$HOME/.cfg" ]]; then
        info "Initialising .tmux submodule via bare repo..."
        git --git-dir="$HOME/.cfg/" --work-tree="$HOME" submodule update --init -- .tmux
        ok ".tmux submodule"
    else
        warn "Bare dotfiles repo (~/.cfg) not found — skipping submodule init"
    fi
}

# ---------------------------------------------------------------------------
# 10. fzf key bindings & completion
# ---------------------------------------------------------------------------

section_fzf() {
    info "--- fzf setup ---"
    if [[ -f "$HOME/.fzf.zsh" ]]; then
        ok "fzf shell integration"
    else
        if [[ "$OS" == "Darwin" ]] && [[ -d "$(brew --prefix)/opt/fzf" ]]; then
            "$(brew --prefix)"/opt/fzf/install --key-bindings --completion --no-update-rc --no-bash --no-fish
        elif [[ -d "$HOME/.fzf" ]]; then
            "$HOME/.fzf/install" --key-bindings --completion --no-update-rc --no-bash --no-fish
        else
            warn "fzf installed but shell integration not configured — run 'fzf --install' manually"
        fi
    fi
}

# =============================================================================
# Main
# =============================================================================

echo ""
echo "========================================"
echo "  Dotfiles setup — $(uname -s)/$(uname -m)"
echo "========================================"
echo ""

sections=(
    "Package manager:section_package_manager"
    "CLI tools:section_cli_tools"
    "Cask apps (macOS):section_cask_apps"
    "Oh-My-Zsh + plugins:section_omz"
    "Rust:section_rust"
    "NVM / Node.js:section_nvm"
    "Python / pyenv:section_python"
    "Doom Emacs:section_doom"
    "Git submodules:section_submodules"
    "fzf shell integration:section_fzf"
)

for entry in "${sections[@]}"; do
    label="${entry%%:*}"
    func="${entry##*:}"
    echo ""
    if confirm "Install/setup ${label}?"; then
        "$func"
    else
        warn "Skipped: ${label}"
    fi
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "  - Open a new terminal to pick up shell changes"
echo "  - Run 'p10k configure' if the Powerlevel10k prompt needs tuning"
echo "  - Run '~/.emacs.d/bin/doom sync' after changing Doom Emacs config"
echo ""
