(setq zotxt-default-bibliography-style "emacs-zotxt")
(setq-default org-enforce-todo-dependencies t)
(setq-default org-icalendar-include-todo t)

(setq org-journal-dir "~/org/journal")
(setq org-agenda-clockreport-parameter-plist
      (quote (:link t :maxlevel 5 :fileskip0 t :compact t :narrow 80)))
(setq org-agenda-files (list
                        "~/org"
                        "~/org/notes"))

(add-hook 'org-mode-hook 'turn-on-auto-fill)
(add-hook 'org-mode-hook
          (lambda ()
            (setq fill-column 80)
            (org-zotxt-mode 1)
            (define-key org-mode-map
              (kbd (cond ((eq system-type 'darwin) "H-i")
                         ((eq system-type 'gnu/linux) "s-i"))) 'org-clock-in)
            (define-key org-mode-map
              (kbd (cond ((eq system-type 'darwin) "H-o")
                         ((eq system-type 'gnu/linux) "s-o"))) 'org-clock-out)
            (define-key org-mode-map (kbd "H-d") 'org-todo)
            (define-key org-mode-map (kbd "M-+") 'text-scale-increase)
            (define-key org-mode-map (kbd "M-°") 'text-scale-decrease)
            (define-key org-mode-map (kbd "C-c \" \"")
              (lambda () (interactive) (org-zotxt-insert-reference-link '(4))))))
(add-hook 'org-journal-mode-hook
          (lambda ()
            (define-key org-journal-mode-map
              (kbd "C-x C-s") 'org-journal-save-entry-and-exit)))

(setq calendar-week-start-day 1)

(setq reftex-default-bibliography '("~/Papers/library.bib"))
(setq org-ref-default-bibliography '("~/Papers/library.bib")
      org-ref-pdf-directory "~/Papers/pdf/"
      org-ref-bibliography-notes "~/Papers/reading_list.org")
(setq bibtex-completion-pdf-open-function
      (lambda (fpath)
        (cond ((eq system-type 'darwin) (start-process "open" "*open*" "open" fpath))
              ((eq system-type 'gnu/linux) (start-process "evince" "*evince*" "evince" fpath)))))

(setq bibtex-completion-pdf-field "file")
(setq bibtex-completion-pdf-symbol "⌘")
(setq bibtex-completion-notes-symbol "✎")

(setq org-refile-targets '((org-agenda-files . (:maxlevel . 6))))
(setq org-refile-use-outline-path 'file)
(setq org-refile-allow-creating-parent-nodes 'confirm)

(defun my-buffer-face-mode-variable ()
  "Set font to a variable width (proportional) fonts in current buffer"
  (interactive)
  (setq buffer-face-mode-face '(:family "Roboto Slab"
                                        :height 120
                                        :width normal))
  (buffer-face-mode))
(add-hook 'org-mode-hook 'my-buffer-face-mode-variable)
(add-hook 'markdown-mode-hook 'my-buffer-face-mode-variable)

(setq org-capture-templates
      '(("n" "Notes" entry
         (file "~/org/inbox.org") "* %^{Description} %^g\n Added: %U\n%?")
        ("t" "TODO" entry
         (file "~/org/inbox.org") "* TODO %^{Title}")
        ("w" "Work TODO" entry
         (file "~/org/work.org") "* TODO %^{Title}")))

(setq org-journal-dir "~/org/journal/")
(setq org-bullets-bullet-list '("◉" "○" "♢" "☐" "►" "◄" "△" "×"))
(defun org-journal-save-entry-and-exit()
  "Simple convenience function.
  Saves the buffer of the current day's entry and kills the window
  Similar to org-capture like behavior"
  (interactive)
  (save-buffer)
  (kill-buffer-and-window))


(setq org-agenda-category-icon-alist
      `(("Work" ,(list (all-the-icons-faicon "cogs")) nil nil :ascent center)
        ("Personal" ,(list (all-the-icons-material "person")) nil nil :ascent center)
        ("Reading" ,(list (all-the-icons-faicon "book")) nil nil :ascent center)))
