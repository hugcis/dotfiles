# Dotfiles

My dotfiles, managed as a **bare git repository** at `~/.cfg` with `$HOME` as the work tree.

## How it works

This uses the bare repo pattern: a git repo lives at `~/.cfg/` and tracks files
directly in `$HOME` without a `.git` directory polluting the home folder. All
git operations go through the `config` alias defined in `.zshrc`:

```bash
alias config='git --git-dir=$HOME/.cfg/ --work-tree=$HOME'
```

This means `config status`, `config add`, `config commit`, etc. work exactly
like regular git commands but operate on the dotfiles repo.

New files in `$HOME` are **not tracked by default**. The bare repo's own ignore
file (`~/.cfg/info/exclude`) contains a single `*`, so every untracked file is
ignored and `config add -A` can only ever stage changes to already-tracked files.
To start tracking a new file, force it:

```bash
config add -f ~/.some-new-dotfile
```

Note this is `~/.cfg/info/exclude`, **not** `~/.gitexclude`. The latter is the
global `core.excludesfile` and applies to every repo on the machine; putting `*`
there would break unrelated projects.

## File structure

### Shell (zsh)

The shell config is split by concern and OS:

| File | Purpose |
| ------ | --------- |
| `.zshenv` | Shared environment variables (loaded for all shells) |
| `.zshenv.macos` | macOS-specific env: Homebrew, PATH, Rust, Docker |
| `.zshenv.linux` | Linux-specific env: keychain SSH agent |
| `.zshrc` | Shared interactive config: oh-my-zsh, aliases, NVM lazy-loading |
| `.zshrc.macos` | macOS interactive: pyenv, Nix, Homebrew completions, Alacritty/Zellij integration |
| `.zshrc.linux` | Linux interactive: tmux TERM fix |
| `.config/starship.toml` | Starship prompt config (if customized) |

OS-specific files are sourced conditionally via `case "$OSTYPE"` at the end of
`.zshenv` and `.zshrc`.

### Editors

**Vim** (`.vimrc`, `.vim/`): Uses Vim's native `pack/` plugin system. Plugins
live in `.vim/pack/latex/start/` as git submodules (note: the `latex` directory
name is historical — it contains general plugins too). Key plugins: vimtex,
vim-airline, vim-fugitive, UltiSnips.

**Doom Emacs** (`.doom.d/`): Primary editor. `init.el` declares modules,
`config.el` has package configuration, `packages.el` declares extra packages.
`org-config.el` (tangled from `org-config.org`) contains extensive org-mode,
org-roam, org-agenda, and bibliography setup.

### Terminal

- `.config/alacritty/alacritty.toml` — Alacritty terminal config (TOML format)
- `.config/zellij/config.kdl` — Zellij terminal multiplexer
- `.tmux.conf` / `.tmux.conf.local` — tmux config (uses gpakosz/.tmux framework via submodule at `.tmux/`)

### Git

- `.gitconfig` — User identity, aliases (`co`, `ci`, `st`, `br`, `hist`, `la`, `sync`), SSH credential helpers, per-org URL rewrites
- `.gitexclude` — Global gitignore patterns (LaTeX build artifacts, Python bytecode, macOS files)
- `.gitmodules` — Submodule declarations (`.tmux`)

## Package management

Packages are declared in tracked files rather than managed imperatively:

| File | OS | Format |
|------|----|--------|
| `Brewfile` | macOS | Homebrew bundle format (`brew`, `cask`, `tap`) |
| `.packages.arch` | Arch Linux | Plain text, one package per line (comments with `#`) |

Two shell functions (defined in `.zshrc`) keep things in sync:

### `dotfiles-sync`

Pulls the latest dotfiles and installs any missing packages in one step:

1. `config pull --rebase` — fast-forward the bare repo
2. Detects the OS and runs the appropriate package installer:
   - **macOS:** `brew bundle install --file=~/Brewfile`
   - **Arch Linux:** `sudo pacman -S --needed` from `~/.packages.arch`
3. `exec zsh` — reloads the shell to pick up any config changes

Also available as `config sync` (git alias).

### `dotfiles-doctor`

Reports missing tools without changing anything:

- Checks for common CLI tools: `git`, `zsh`, `fzf`, `rg`, `bat`
- **macOS:** checks for Homebrew and key formulae (`fd`, `lsd`, `cmake`, `tmux`, `zellij`, `uv`)
- **Arch Linux:** walks `.packages.arch` and reports any uninstalled packages

Prints "All good!" if everything is present, or lists each missing tool.

## Installation

```bash
curl -L https://gist.github.com/hugcis/73191d55b6bc77815fc4df3b9a62a9a3/raw/ | /bin/bash
```

### After cloning on a new machine

The pre-commit guard is not carried by git. Recreate it:

```bash
cp ~/.config/agent-stack/pre-commit.sample ~/.cfg/hooks/pre-commit
chmod +x ~/.cfg/hooks/pre-commit
```
