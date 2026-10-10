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

Managed by home-manager (`~/.config/home-manager/modules/terminal.nix`):

- Alacritty — settings declared in the module; binary from nix (the brew cask
  only keeps the `.app` registered for Spotlight)
- Zellij — binary from nix; config stays raw KDL at `.config/home-manager/configs/zellij.kdl`
- `.tmux.conf` / `.tmux.conf.local` — tmux config (gpakosz/.tmux framework);
  `.tmux.conf` is a home-manager symlink to `configs/tmux.conf`, local overrides
  stay in the unmanaged `~/.tmux.conf.local`

### Git

- `~/.config/home-manager/modules/git.nix` — user identity, aliases (`co`, `ci`, `st`, `br`, `hist`, `la`, `sync`), SSH credential helpers, per-org URL rewrites; writes `~/.config/git/config`
- `~/.gitexclude` — home-manager symlink to `configs/gitexclude`: global ignore patterns (LaTeX build artifacts, Python bytecode, macOS files)
- `.gitmodules` — Submodule declarations (`.tmux`)

## Home manager

`~/.config/home-manager` is a nix flake that owns the shells (the raw zsh
files under `configs/zsh/` are symlinked into `$HOME`), git, starship, the
terminal multiplexers, and the cross-platform CLI package list. Hosts live
in `hosts/` and the registry in `flake.nix`:

| Host | System | Channel |
|------|--------|---------|
| `hugo@mac` | aarch64-darwin | nixpkgs-unstable + HM master |
| `hugo@pi` | aarch64-linux (Arch ARM) | nixos-26.05 + HM release-26.05 |
| `hugo@remote-mistral` | x86_64-linux (RHEL/Ubuntu-like) | nixos-26.05 + HM release-26.05 |

Switch with `hm` (host auto-detected via marker file or uname; `hm <host>`
to override; any other args pass through to home-manager). New files under
this tree need an explicit `config add -f` (the bare repo ignores everything
by default). CI (`.github/workflows/home-manager.yml`) evaluates every host
on every system and builds each host's activation package on a matching
runner.

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

## Setting up the agent stack on a new machine

`~/.config/agent-stack/` renders one shared roster of coding agents into four
harnesses (pi, opencode, vibe, Claude Code) and installs the shared skills. Three
pieces of it are deliberately **not** in git — this repo is public — so a fresh
clone needs them recreated by hand, in this order.

```bash
# 1. Bootstrap the ignore rule, in dry form. install.sh creates ~/.cfg/info/exclude
#    (git never clones it) and then stops, because there is no profile yet.
~/.config/agent-stack/install.sh

# 2. Machine profile: endpoints, per-harness provider spellings, and which model
#    fills each abstract slot. Never committed.
cp ~/.config/agent-stack/profile.example.yaml ~/.config/agent-stack/profile.yaml
$EDITOR ~/.config/agent-stack/profile.yaml   # replace every REPLACE-ME

# 3. Pre-commit denylist: the strings this machine must never publish. Never
#    committed — a denylist in a public repo publishes what it protects.
cp ~/.config/agent-stack/denylist.example.txt ~/.config/agent-stack/denylist.txt
$EDITOR ~/.config/agent-stack/denylist.txt   # one extended-regex pattern per line

# 4. Pre-commit guard. Git does not clone hooks either, and the hook refuses to
#    run without step 3, so every commit is blocked until both are in place.
mkdir -p ~/.cfg/hooks
cp ~/.config/agent-stack/pre-commit.sample ~/.cfg/hooks/pre-commit
chmod +x ~/.cfg/hooks/pre-commit

# 5. Now the real run: skills symlinked into each harness, agents rendered,
#    profile.env written, and profile.env sourced from ~/.zshenv.<os>.
~/.config/agent-stack/install.sh
```

Step 1 is safe to repeat: it only appends the `*` rule when `info/exclude` does
not already contain one. Run `install.sh` again after editing `profile.yaml`,
`roster.yaml`, or the prompts.

`~/.config/agent-stack/render.py` does the rendering and can be run on its own
(`python3 ~/.config/agent-stack/render.py`) once `profile.yaml` exists. It
overwrites the per-harness agent directories and the `AGENTS.md`/`CLAUDE.md`
files wholesale, keeping timestamped copies of anything it displaces under
`~/.local/state/agent-stack/`.
