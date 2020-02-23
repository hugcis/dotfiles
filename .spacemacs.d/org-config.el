(setq zotxt-default-bibliography-style "emacs-zotxt")
(setq-default org-enforce-todo-dependencies t)
(setq-default org-icalendar-include-todo t)

(setq org-agenda-clockreport-parameter-plist
      (quote (:link t :maxlevel 5 :fileskip0 t :compact t :narrow 80)))
(setq org-agenda-files '("~/org"))
(add-hook 'org-mode-hook 'turn-on-auto-fill)
(add-hook 'org-mode-hook
          (lambda ()
            (setq fill-column 80)
            (org-zotxt-mode 1)
            (define-key org-mode-map (kbd "H-i") 'org-clock-in)
            (define-key org-mode-map (kbd "H-o") 'org-clock-out)
            (define-key org-mode-map (kbd "H-d") 'org-todo)
            (define-key org-mode-map (kbd "C-c \" \"")
              (lambda () (interactive) (org-zotxt-insert-reference-link '(4))))))

(setq calendar-week-start-day 1)

(setq org-ref-default-bibliography '("~/Papers/library.bib"))
(setq org-refile-targets '((org-agenda-files . (:maxlevel . 6))))

(defun my-buffer-face-mode-variable ()
  "Set font to a variable width (proportional) fonts in current buffer"
  (interactive)
  (setq buffer-face-mode-face '(:family "Roboto Slab"
                                        :height 150
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
