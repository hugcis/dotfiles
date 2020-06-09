(setq zotxt-default-bibliography-style "emacs-zotxt")
(setq-default org-enforce-todo-dependencies t)
(setq-default org-icalendar-include-todo t)
(setq org-agenda-files (list
                        "~/org"
                        "~/Papers/reading_list.org"))

(with-eval-after-load 'org-journal
  (add-to-list 'org-agenda-files org-journal-dir)
  )

(setq org-agenda-clockreport-parameter-plist
      (quote (:link t :maxlevel 5 :fileskip0 t :compact t :narrow 80)))

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

;; Org-ref config
(with-eval-after-load 'org-ref
  (setq reftex-default-bibliography '("~/Papers/library.bib"))
  (setq org-ref-default-bibliography '("~/Papers/library.bib")
        org-ref-pdf-directory "~/Papers/pdf/"
        org-ref-bibliography-notes "~/org/roam/notes")
  (setq org-ref-notes-function
        (lambda (thekey)
          (let ((bibtex-completion-bibliography (org-ref-find-bibliography)))
            (bibtex-completion-edit-notes
             (list (car (org-ref-get-bibtex-key-and-file thekey)))))))
  (setq bibtex-completion-notes-template-multiple-files
        "#+TITLE: Notes on: ${author-or-editor} (${year}): ${title}\n\n- source :: cite:${=key=}\n#+HUGO_BASE_DIR: ~/website/personal-website/
#+HUGO_SECTION: notes
#+ROAM_KEY: cite:${=key=}
\n\n* TODO Summary\n* TODO Comments\n\n
bibliography:~/Papers/library_bibtex.bib
")
)

(setq bibtex-completion-notes-path "~/org/roam/notes")
(setq bibtex-completion-pdf-open-function
      (lambda (fpath)
        (cond ((eq system-type 'darwin) (start-process "open" "*open*" "open" fpath))
              ((eq system-type 'gnu/linux) (start-process "evince" "*evince*" "evince" fpath)))))
(setq bibtex-completion-pdf-field "file")
(setq bibtex-completion-pdf-symbol "⌘")
(setq bibtex-completion-notes-symbol "✎")

(use-package ox-hugo
  :ensure t          ;Auto-install the package from Melpa (optional)
  :after ox)
(use-package org-ref-ox-hugo
  :load-path "elisp/"
  :straight (:host github :repo "hugcis/org-ref-ox-hugo" :branch "custom/overrides")
  :requires ox-hugo
  :after org org-ref ox-hugo
  :config
  (add-to-list 'org-ref-formatted-citation-formats
               '("md"
                 ("article" . "${author}, *${title}*, ${journal}, *${volume}(${number})*, ${pages} (${year}). ${doi}")
                 ("inproceedings" . "${author}, *${title}*, In ${editor}, ${booktitle} (pp. ${pages}) (${year}). ${address}: ${publisher}.")
                 ("book" . "${author}, *${title}* (${year}), ${address}: ${publisher}.")
                 ("phdthesis" . "${author}, *${title}* (Doctoral dissertation) (${year}). ${school}, ${address}.")
                 ("inbook" . "${author}, *${title}*, In ${editor} (Eds.), ${booktitle} (pp. ${pages}) (${year}). ${address}: ${publisher}.")
                 ("incollection" . "${author}, *${title}*, In ${editor} (Eds.), ${booktitle} (pp. ${pages}) (${year}). ${address}: ${publisher}.")
                 ("proceedings" . "${editor} (Eds.), _${booktitle}_ (${year}). ${address}: ${publisher}.")
                 ("unpublished" . "${author}, *${title}* (${year}). Unpublished manuscript.")
                 ("misc" . "${author} (${year}). *${title}*. Retrieved from [${howpublished}](${howpublished}). ${note}.")
                 (nil . "${author}, *${title}* (${year}).")))
  )


(setq org-refile-targets '((org-agenda-files . (:maxlevel . 6))))
(setq org-refile-use-outline-path 'file)
(setq org-refile-allow-creating-parent-nodes 'confirm)

(defun my/buffer-face-mode-variable ()
  "Set font to a variable width (proportional) fonts in current buffer"
  (interactive)
  (setq buffer-face-mode-face '(:family "Roboto Slab"
                                        :height 150
                                        :width normal))
  (buffer-face-mode))
(add-hook 'markdown-mode-hook 'my/buffer-face-mode-variable)

(setq org-capture-templates
      '(("n" "Notes" entry
         (file "~/org/inbox.org") "* %^{Description} %^g\n Added: %U\n%?")
        ("t" "TODO" entry
         (file "~/org/inbox.org") "* TODO %^{Title}")
        ("w" "Work TODO" entry
         (file "~/org/work.org") "* TODO %^{Title}")))

(setq org-bullets-bullet-list '("◉" "○" "♢" "☐" "►" "◄" "△" "×"))
(setq org-ellipsis "⤵")

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

(defun my/style-org ()
  (my/buffer-face-mode-variable)
  (setq line-spacing 0.1
        org-pretty-entities t
        org-startup-indented t)
  (variable-pitch-mode +1)
  (mapc
   (lambda (face) ;; Other fonts with fixed-pitch.
     (set-face-attribute face nil :inherit 'fixed-pitch))
   (list 'org-code
         'org-block
         'org-table
         'org-verbatim
         'org-block-begin-line
         'org-block-end-line
         'org-meta-line
         'org-document-info-keyword)))

(add-hook 'org-mode-hook 'my/style-org)

;; Org-roam config
(with-eval-after-load 'org-roam
  (add-hook 'org-roam-backlinks-mode-hook 'my/style-org)

  (setq org-roam-graphviz-executable (executable-find "neato"))
  (setq org-roam-graphviz-extra-options '(("overlap" . "false")))
  (setq org-roam-completion-system 'helm)
  (setq org-roam-capture-templates '(("d" "default" plain #'org-roam--capture-get-point "%?"
                                      :file-name "%<%Y%m%d%H%M%S>-${slug}"
                                      :head "#+TITLE: ${title}\n#+HUGO_BASE_DIR: ~/website/personal-website/\n#+HUGO_SECTION: notes\n\n"
                                      :unnarrowed t))))

(with-eval-after-load 'org
  (defun my/org-roam--backlinks-list (file)
    (if (org-roam--org-roam-file-p file)
        (--reduce-from
         (concat acc (format "- [[file:%s][%s]]\n"
                             (file-relative-name (car it) org-roam-directory)
                             (org-roam--get-title-or-slug (car it))))
         "" (delete-dups (org-roam-sql [:select [from]
                                                :from links
                                                :where (= to $s1)
                                                :and from :not :like $s2] file "%private%")))
      ""))
  (defun my/org-export-preprocessor (_backend)
    (let ((links (my/org-roam--backlinks-list (buffer-file-name))))
      (unless (string= links "")
        (save-excursion
          (goto-char (point-max))
          (insert (concat "\n* Backlinks\n" links))))))
  (add-hook 'org-export-before-processing-hook 'my/org-export-preprocessor)
)


(with-eval-after-load 'ox-hugo
  (setq python-graph-script-location "/Users/hugo/scripts/dot_to_json.py")
  (setq json-graph-location "/Users/hugo/website/personal-website/static/js/graph.json")
  (defun my/run-python-script-roam-graph (graph-fname output-fname)
    (insert (shell-command-to-string (format "python %s %s %s"
                                             python-graph-script-location
                                             graph-fname
                                             output-fname))))
  (defun my/export-roam-graph ()
    (interactive)
    (let ((current-prefix-arg 16)) ;; emulate C-u
      (call-interactively 'org-roam-graph) ;; invoke align-regexp interactively
      )
    )
    ;; (my/run-python-script-roam-graph ( (universal-argument) nil) json-graph-location))

  (defun my/org-export-all-roam ()
    (interactive)
    (mapc (lambda (fPath)
            (with-temp-buffer
              (print fPath)
              (find-file-read-only fPath)
              (org-hugo-export-to-md)
              (kill-buffer)))
          (org-roam--list-files "/Users/hugo/org/roam"))))
;; Using Deft in org-mode
(setq deft-directory "~/org/roam/")
