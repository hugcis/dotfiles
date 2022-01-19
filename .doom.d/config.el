;;; $DOOMDIR/config.el -*- lexical-binding: t; -*-

;; Place your private configuration here! Remember, you do not need to run 'doom
;; sync' after modifying this file!


;; Some functionality uses this to identify you, e.g. GPG configuration, email
;; clients, file templates and snippets.
(setq user-full-name "Hugo Cisneros"
      user-mail-address "hmj.cisneros@gmail.com")

;; Doom exposes five (optional) variables for controlling fonts in Doom. Here
;; are the three important ones:
;;
;; + `doom-font'
;; + `doom-variable-pitch-font'
;; + `doom-big-font' -- used for `doom-big-font-mode'; use this for
;;   presentations or streaming.
;;
;; They all accept either a font-spec, font string ("Input Mono-12"), or xlfd
;; font string. You generally only need these two:
(setq doom-font (font-spec :family "Meslo LG S for Powerline" :size 12))
;       doom-variable-pitch-font (font-spec :family "sans" :size 13))

;; There are two ways to load a theme. Both assume the theme is installed and
;; available. You can either set `doom-theme' or manually load a theme with the
;; `load-theme' function. This is the default:
(setq doom-theme 'doom-one)

;; If you use `org' and don't want your org files in the default location below,
;; change `org-directory'. It must be set before org loads!
(setq org-directory "~/org/")

;; This determines the style of line numbers in effect. If set to `nil', line
;; numbers are disabled. For relative line numbers, set this to `relative'.
(setq display-line-numbers-type t)


;; Here are some additional functions/macros that could help you configure Doom:
;;
;; - `load!' for loading external *.el files relative to this one
;; - `use-package!' for configuring packages
;; - `after!' for running code after a package has loaded
;; - `add-load-path!' for adding directories to the `load-path', relative to
;;   this file. Emacs searches the `load-path' when you load packages with
;;   `require' or `use-package'.
;; - `map!' for binding new keys
;;
;; To get information about any of these functions/macros, move the cursor over
;; the highlighted symbol at press 'K' (non-evil users must press 'C-c c k').
;; This will open documentation for it, including demos of how they are used.
;;
;; You can also try 'gd' (or 'C-c c d') to jump to their definition and see how
;; they are implemented.
(use-package! evil-escape
  :config
  (setq-default evil-escape-key-sequence "fd")
  (setq-default evil-escape-delay 0.15)
  (setq-default evil-escape-unordered-key-sequence nil)
  (setq-default evil-escape-inhibit-functions nil)
  (evil-escape-mode))
(use-package! evil-surround
  :config
  (global-evil-surround-mode 1))

(use-package! org-roam
  :config
  (setq org-roam-directory (expand-file-name "~/org/roam"))
  :init
  (map! :leader
        :prefix "n"
        :desc "org-roam" "l" #'org-roam-buffer
        :desc "org-roam-node-insert" "i" #'org-roam-node-insert
        :desc "org-roam-node-find" "f" #'org-roam-node-find
        :desc "org-roam-ref-find" "r" #'org-roam-ref-find
        :desc "org-roam-show-graph" "g" #'org-roam-show-graph
        :desc "org-roam-capture" "c" #'org-roam-capture
        :desc "org-roam-dailies-capture-today" "j" #'org-roam-dailies-capture-today)
  :after org)

(use-package! ox-hugo
  :after ox)
(use-package! org-ref
  :config
  (setq org-ref-csl-default-style (expand-file-name "~/custom-org-citeproc-export.csl"))
  (setq org-cite-csl-locales-dir (expand-file-name "~/csl-locales/"))
  :after org)

(use-package! org-caldav
  :after org)
(use-package! org-super-agenda
  :hook (org-agenda-mode . org-super-agenda-mode))

(use-package! lsp-pyright
  :hook (python-mode . (lambda ()
                          (require 'lsp-pyright)
                          (lsp))))  ; or lsp-deferred
(setq lsp-enable-file-watchers nil)
(setq lsp-headerline-breadcrumb-enable t)
;;
(setq ns-alternate-modifier 'meta)
(setq ns-right-alternate-modifier 'none)
;;
;; Stop polluting the directory with auto-saved files and backup
(setq auto-save-default nil)
(setq make-backup-files nil)
(setq auto-save-list-file-prefix nil)
;; Prompt for local variables
(setq-default enable-local-variables t)
;; Well, it's more so that you know this option
(setq kill-whole-line t)
(setq kill-read-only-ok t)
(setq require-final-newline t)

;; Scrolling done right
(setq scroll-error-top-bottom t)

;; Number of lines of continuity when scrolling by screenfulls
(setq next-screen-context-lines 0)

(setq helm-buffer-list-reorder-fn #'helm-buffers-reorder-buffer-list)

(setq ispell-program-name "aspell")
(setq flycheck-textlint-config "/Users/hugo/.textlintrc")
(setq flycheck-textlint-executable "/Users/hugo/node_modules/.bin/textlint")
(setq flycheck-textlint-plugin-alist '((markdown-mode . "@textlint/markdown")
                                       (gfm-mode . "@textlint/markdown")
                                       (latex-mode . "latex2e")
                                       (t . "@textlint/text")))
(add-hook! 'latex-mode-hook (flycheck-add-next-checker 'lsp 'textlint))
(display-time-mode 1)

(setq magit-display-buffer-function #'magit-display-buffer-fullframe-status-v1)

(after! evil-maps
  (define-key evil-insert-state-map (kbd "<C-tab>") 'yas-expand)
  (define-key evil-motion-state-map (kbd "SPC") nil)
  (define-key evil-motion-state-map (kbd "RET") nil))

(global-set-key (kbd (cond
                ((eq system-type 'darwin) "s-r")
                ((eq system-type 'gnu/linux) "M-²"))) 'next-multiframe-window)

(setq reftex-external-file-finders
        '(("tex" . "kpsewhich -format=.tex %f")
          ("bib" . "kpsewhich -format=.bib %f")))
(setq bibtex-completion-pdf-field "file")

(add-hook 'text-mode-hook 'turn-on-auto-fill)
(defun my/cleanup-text-mode ()
  (setq fill-column 80)
  (display-line-numbers-mode -1)
  (display-fill-column-indicator-mode -1)
  (setq isearch-regexp-lax-whitespace t)
  (setq search-whitespace-regexp "[ \t\r\n]+"))
(add-hook 'text-mode-hook #'my/cleanup-text-mode)
(add-hook 'org-mode-hook #'my/cleanup-text-mode)
(add-hook 'markdown-mode-hook #'my/cleanup-text-mode)

(add-hook 'c-mode-hook 'flycheck-mode)

(setq exec-path-from-shell-variables
      '("PATH" "MANPATH" "SSH_AGENT_PID"  "SSH_AUTH_SOCK"))
(setq exec-path-from-shell-arguments nil)
(when (memq window-system '(mac ns x))
  (exec-path-from-shell-initialize))

(setq epg-pinentry-mode 'loopback)

(setq nnrss-ignore-article-fields '(description slash:comments
                                                slash:hit_parade))

(defun python-symbols()
  (mapc (lambda (pair) (push pair prettify-symbols-alist)) '(("->" . "➔")))
  (prettify-symbols-mode +1))
(defun rust-symbols()
  (mapc (lambda (pair) (push pair prettify-symbols-alist)) '(("->" . "➔")))
  (prettify-symbols-mode +1))
(add-hook 'rust-mode-hook 'rust-symbols)
(add-hook 'python-mode-hook (lambda () (python-symbols)))

(after! tramp (setenv "SHELL" "/bin/bash"))
(after! org (load! "org-config.el"))
