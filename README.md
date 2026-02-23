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

New files in `$HOME` are **not tracked by default**. The `.gitexclude` file
(referenced via `core.excludesfile` in `.gitconfig`) ignores everything, so
`config status` only shows changes to files that have been explicitly added.
To start tracking a new file, add it manually:

```bash
config add ~/.some-new-dotfile
```

## File structure

### Shell (zsh)

The shell config is split by concern and OS:

| File | Purpose |
|------|---------|
| `.zshenv` | Shared environment variables (loaded for all shells) |
| `.zshenv.macos` | macOS-specific env: Homebrew, PATH, Rust, Docker |
| `.zshenv.linux` | Linux-specific env: keychain SSH agent |
| `.zshrc` | Shared interactive config: oh-my-zsh, aliases, NVM lazy-loading |
| `.zshrc.macos` | macOS interactive: pyenv, Nix, Homebrew completions, Alacritty/Zellij integration |
| `.zshrc.linux` | Linux interactive: tmux TERM fix |
| `.p10k.zsh` | Powerlevel10k theme config (generated via `p10k configure`) |

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

- `.gitconfig` — User identity, aliases (`co`, `ci`, `st`, `br`, `hist`, `la`), SSH credential helpers, per-org URL rewrites
- `.gitexclude` — Global gitignore patterns (LaTeX build artifacts, Python bytecode, macOS files)
- `.gitmodules` — Submodule declarations (`.tmux`)

## Installation

```bash
curl -L https://gist.github.com/hugcis/73191d55b6bc77815fc4df3b9a62a9a3/raw/ | /bin/bash
```
