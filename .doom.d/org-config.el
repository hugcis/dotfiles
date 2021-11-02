(setq org-todo-keywords
    (quote ((sequence "TODO(t)" "NEXT(n)" "|" "DONE(d)")
            (sequence "WAITING(w@/!)" "HOLD(h@/!)" "|" "CANCELLED(c@/!)"))))

(setq-default org-enforce-todo-dependencies t)

(setq org-todo-keyword-faces
    (quote (("TODO" :foreground "red" :weight bold)
            ("NEXT" :foreground "blue" :weight bold)
            ("DONE" :foreground "forest green" :weight bold)
            ("WAITING" :foreground "orange" :weight bold)
            ("HOLD" :foreground "magenta" :weight bold)
            ("CANCELLED" :foreground "forest green" :weight bold)
            ("MEETING" :foreground "forest green" :weight bold)
            ("PHONE" :foreground "forest green" :weight bold))))
;; I don't wan't the keywords in my exports
(setq-default org-export-with-todo-keywords nil)

(with-eval-after-load 'org-superstar
  (setq org-superstar-item-bullet-alist
        '((?* . ?•)
          (?+ . ?➤)
          (?- . ?•)))
  (setq org-superstar-headline-bullets-list '(?\s))
  (setq org-superstar-special-todo-items t)
  (setq org-superstar-remove-leading-stars t)
  ;; Enable custom bullets for TODO items
  (setq org-superstar-todo-bullet-alist
        '(("TODO" . ?☐)
          ("NEXT" . ?✒)
          ("HOLD" . ?✰)
          ("WAITING" . ?☕)
          ("CANCELLED" . ?✘)
          ("DONE" . ?✔)))
  (org-superstar-restart))
(setq org-ellipsis " ▼ ")

(defun my/buffer-face-mode-variable ()
  "Set font to a variable width (proportional) fonts in current buffer"
  (interactive)
  (setq buffer-face-mode-face '(:family "Roboto Slab"
                                :height 150
                                :width normal))
  (buffer-face-mode))

(setq org-hide-emphasis-markers t)

(defun my/set-general-faces-org ()
  ;; I have removed indentation to make the file look cleaner
  (org-indent-mode -1)
  (my/buffer-face-mode-variable)
  (setq line-spacing 0.1
        org-pretty-entities t
        org-startup-indented t
        org-adapt-indentation nil)
  (variable-pitch-mode +1)
  (mapc
   (lambda (face) ;; Other fonts that require it are set to fixed-pitch.
     (set-face-attribute face nil :inherit 'fixed-pitch))
   (list 'org-block
         'org-table
         'org-verbatim
         'org-block-begin-line
         'org-block-end-line
         'org-meta-line
         'org-date
         'org-drawer
         'org-property-value
         'org-special-keyword
         'org-document-info-keyword))
  (mapc ;; This sets the fonts to a smaller size
   (lambda (face)
     (set-face-attribute face nil :height 0.8))
   (list 'org-document-info-keyword
         'org-block-begin-line
         'org-block-end-line
         'org-meta-line
         'org-drawer
         'org-property-value
         )))

(defun my/set-specific-faces-org ()
  (set-face-attribute 'org-code nil
                      :inherit '(shadow fixed-pitch))
  ;; Without indentation the headlines need to be different to be visible
  (set-face-attribute 'org-level-1 nil
                      :height 1.25
                      :foreground "#BEA4DB")
  (set-face-attribute 'org-level-2 nil
                      :height 1.15
                      :foreground "#A382FF"
                      :slant 'italic)
  (set-face-attribute 'org-level-3 nil
                      :height 1.1
                      :foreground "#5E65CC"
                      :slant 'italic)
  (set-face-attribute 'org-level-4 nil
                      :height 1.05
                      :foreground "#ABABFF")
  (set-face-attribute 'org-level-5 nil
                      :foreground "#2843FB")
  (set-face-attribute 'org-date nil
                      :foreground "#ECBE7B"
                      :height 0.8)
  (set-face-attribute 'org-document-title nil
                      :foreground "DarkOrange3"
                      :height 1.3)
  (set-face-attribute 'org-ellipsis nil
                      :foreground "#4f747a" :underline nil)
  (set-face-attribute 'variable-pitch nil
                      :family "Roboto Slab" :height 1.2))

(defun my/set-keyword-faces-org ()
  (mapc (lambda (pair) (push pair prettify-symbols-alist))
        '(;; Syntax
          ("TODO" .     "")
          ("DONE" .     "")
          ("WAITING" .  "")
          ("HOLD" .     "")
          ("NEXT" .     "")
          ("CANCELLED" . "")
          ("#+begin_quote" . "“")
          ("#+end_quote" . "”")))
  (prettify-symbols-mode +1)
  (org-superstar-mode +1)
  )

(defun my/style-org ()
  (my/set-general-faces-org)
  (my/set-specific-faces-org)
  (my/set-keyword-faces-org)
  )
(add-hook 'org-mode-hook 'my/style-org)

(setq org-agenda-skip-scheduled-if-done t
      org-agenda-skip-deadline-if-done t
      org-agenda-include-deadlines t
      org-agenda-block-separator #x2501
      org-agenda-compact-blocks t
      org-agenda-start-with-log-mode t)
(with-eval-after-load 'org-journal
  (setq org-agenda-files '("~/org" "~/org/roam/notes/")))
(setq org-agenda-clockreport-parameter-plist
      (quote (:link t :maxlevel 5 :fileskip0 t :compact t :narrow 80)))
(setq org-agenda-deadline-faces
      '((1.0001 . org-warning)              ; due yesterday or before
        (0.0    . org-upcoming-deadline)))  ; due today or later

(setq-default org-icalendar-include-todo t)
(setq org-combined-agenda-icalendar-file "~/org/calendar.ics")
(setq org-icalendar-combined-name "Hugo Org")
(setq org-icalendar-use-scheduled '(todo-start event-if-todo event-if-not-todo))
(setq org-icalendar-use-deadline '(todo-due event-if-todo event-if-not-todo))
(setq org-icalendar-timezone "Europe/Paris")
(setq org-icalendar-store-UID t)
(setq org-icalendar-alarm-time 30)
(setq french-holiday
      '((holiday-fixed 1 1 "Jour de l'an")
        (holiday-fixed 5 8 "Victoire 45")
        (holiday-fixed 7 14 "Fête nationale")
        (holiday-fixed 8 15 "Assomption")
        (holiday-fixed 11 1 "Toussaint")
        (holiday-fixed 11 11 "Armistice 18")
        (holiday-easter-etc 1 "Lundi de Pâques")
        (holiday-easter-etc 39 "Ascension")
        (holiday-easter-etc 50 "Lundi de Pentecôte")
        (holiday-fixed 1 6 "Épiphanie")
        (holiday-fixed 2 2 "Chandeleur")
        (holiday-fixed 2 14 "Saint Valentin")
        (holiday-fixed 5 1 "Fête du travail")
        (holiday-fixed 5 8 "Commémoration de la capitulation de l'Allemagne en 1945")
        (holiday-fixed 6 21 "Fête de la musique")
        (holiday-fixed 11 2 "Commémoration des fidèles défunts")
        (holiday-fixed 12 25 "Noël")
        ;; fêtes à date variable
        (holiday-easter-etc 0 "Pâques")
        (holiday-easter-etc 49 "Pentecôte")
        (holiday-easter-etc -47 "Mardi gras")
        (holiday-float 6 0 3 "Fête des pères") ;; troisième dimanche de juin
        ;; Fête des mères
        (holiday-sexp
         '(if (equal
               ;; Pentecôte
               (holiday-easter-etc 49)
               ;; Dernier dimanche de mai
               (holiday-float 5 0 -1 nil))
              ;; -> Premier dimanche de juin si coïncidence
              (car (car (holiday-float 6 0 1 nil)))
            ;; -> Dernier dimanche de mai sinon
            (car (car (holiday-float 5 0 -1 nil))))
         "Fête des mères")))
(setq calendar-date-style 'european
      holiday-other-holidays french-holiday
      calendar-mark-holidays-flag t
      calendar-week-start-day 1
      calendar-mark-diary-entries-flag nil)

(defun my/style-org-agenda()
  (my/buffer-face-mode-variable)
  (set-face-attribute 'org-agenda-date nil :height 1.1)
  (set-face-attribute 'org-agenda-date-today nil :height 1.1 :slant 'italic)
  (set-face-attribute 'org-agenda-date-weekend nil :height 1.1))

(add-hook 'org-agenda-mode-hook 'my/style-org-agenda)

(setq org-agenda-breadcrumbs-separator " ❱ "
      org-agenda-current-time-string "⏰ ┈┈┈┈┈┈┈┈┈┈┈ now"
      org-agenda-time-grid '((weekly today require-timed)
                             (800 1000 1200 1400 1600 1800 2000)
                             "---" "┈┈┈┈┈┈┈┈┈┈┈┈┈")
      org-agenda-prefix-format '((agenda . "%i %-12:c%?-12t%b% s")
                                 (todo . " %i %-12:c")
                                 (tags . " %i %-12:c")
                                 (search . " %i %-12:c")))

(setq org-agenda-format-date (lambda (date) (concat "\n" (make-string (window-width) 9472)
                                                    "\n"
                                                    (org-agenda-format-date-aligned date))))
(setq org-cycle-separator-lines 2)
(setq org-agenda-category-icon-alist
      `(("Work" ,(list (all-the-icons-faicon "cogs")) nil nil :ascent center)
        ("Personal" ,(list (all-the-icons-material "person")) nil nil :ascent center)
        ("Calendar" ,(list (all-the-icons-faicon "calendar")) nil nil :ascent center)
        ("Reading" ,(list (all-the-icons-faicon "book")) nil nil :ascent center)))

(setq org-agenda-custom-commands
      '(("z" "Hugo view"
         ((agenda "" ((org-agenda-span 'day)
                      (org-super-agenda-groups
                       '((:name "Today"
                          :time-grid t
                          :date today
                          :todo "TODAY"
                          :scheduled today
                          :order 1)))))
          (alltodo "" ((org-agenda-overriding-header "")
                       (org-super-agenda-groups
                        '(;; Each group has an implicit boolean OR operator between its selectors.
                          (:name "Today"
                           :deadline today
                           :face (:background "black"))
                          (:name "Passed deadline"
                           :and (:deadline past :todo ("TODO" "WAITING" "HOLD" "NEXT"))
                           :face (:background "#7f1b19"))
                          (:name "Work important"
                           :and (:priority>= "B" :category "Work" :todo ("TODO" "NEXT")))
                          (:name "Work other"
                           :and (:category "Work" :todo ("TODO" "NEXT")))
                          (:name "Important"
                           :priority "A")
                          (:priority<= "B"
                           ;; Show this section after "Today" and "Important", because
                           ;; their order is unspecified, defaulting to 0. Sections
                           ;; are displayed lowest-number-first.
                           :order 1)
                          (:name "Papers"
                           :file-path "org/roam/notes")
                          (:name "Waiting"
                           :todo "WAITING"
                           :order 9)
                          (:name "On hold"
                           :todo "HOLD"
                           :order 10)))))))))
(add-hook 'org-agenda-mode-hook 'org-super-agenda-mode)

;; Resume clocking task when emacs is restarted
(org-clock-persistence-insinuate)
;; Show lot of clocking history so it's easy to pick items off the C-F11 list
(setq org-clock-history-length 23)
;; Resume clocking task on clock-in if the clock is open
(setq org-clock-in-resume t)
;; Sometimes I change tasks I'm clocking quickly - this removes clocked tasks with 0:00 duration
(setq org-clock-out-remove-zero-time-clocks t)
;; Clock out when moving task to a done state
(setq org-clock-out-when-done t)
;; Save the running clock and all clock history when exiting Emacs, load it on startup
(setq org-clock-persist t)
;; Include current clocking task in clock reports
(setq org-clock-report-include-clocking-task t)

(add-hook 'org-mode-hook 'turn-on-auto-fill)
(add-hook 'org-mode-hook
          (lambda ()
            (setq fill-column 80)
            (define-key org-mode-map (kbd "s-i") 'org-clock-in)
            (define-key org-mode-map (kbd "s-o") 'org-clock-out)
            (define-key org-mode-map (kbd "s-d") 'org-todo)
            (define-key org-mode-map (kbd "M-+") 'text-scale-increase)
            (define-key org-mode-map (kbd "M-°") 'text-scale-decrease)
            (define-key org-mode-map (kbd "C-c \" \"")
              (lambda () (interactive) (org-zotxt-insert-reference-link '(4))))))

(defun org-journal-save-entry-and-exit()
  "Simple convenience function.
    Saves the buffer of the current day's entry and kills the window
    Similar to org-capture like behavior"
  (interactive)
  (save-buffer)
  (kill-buffer-and-window))

(add-hook 'org-journal-mode-hook
          (lambda ()
            (define-key org-journal-mode-map
              (kbd "C-x C-s") 'org-journal-save-entry-and-exit)))

(setq org-cite-global-bibliography '("~/Papers/library.json"))
(require 'oc-csl)
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
  )

;; Bibtex setup
(setq bibtex-completion-notes-path "~/org/roam/notes")
(setq bibtex-completion-pdf-open-function
      (lambda (fpath)
        (cond ((eq system-type 'darwin) (start-process "open" "*open*" "open" fpath))
              ((eq system-type 'gnu/linux) (start-process "evince" "*evince*" "evince" fpath)))))
(setq bibtex-completion-pdf-field "file")
(setq bibtex-completion-pdf-symbol "⌘")
(setq bibtex-completion-notes-symbol "✎")
(setq bibtex-completion-notes-template-multiple-files
      ":PROPERTIES:\n:ROAM_REFS: cite:${=key=}\n:END:\n#+TITLE: Notes on: ${title} by ${author-or-editor} (${year})\n#+hugo_lastmod: Time-stamp: <>\n#+ROAM_KEY: cite:${=key=}\n\n- source :: cite:${=key=}
\n\n* TODO Summary\n* TODO Comments\n\n
bibliography:~/Papers/library_bibtex.bib")

(setq org-capture-templates
      '(("n" "Notes" entry
         (file "~/org/inbox.org") "* %^{Description} %^g\n Added: %U\n%?")
        ("m" "Meeting notes" entry
         (file "~/org/meetings.org") "* TODO %^{Title} %t\n- %?")
        ("t" "TODO" entry
         (file "~/org/inbox.org") "* TODO %^{Title}")
        ("e" "Event" entry
         (file "~/org/calendar.org") "* %^{Is it a todo?||TODO |NEXT }%^{Title}\n%^t\n%?")
        ("w" "Work TODO" entry
         (file "~/org/work.org") "* TODO %^{Title}")))

(setq org-refile-targets '((org-agenda-files . (:maxlevel . 6))))
(setq org-refile-use-outline-path 'file)
(setq org-refile-allow-creating-parent-nodes 'confirm)

(with-eval-after-load 'org-roam
  ;; Roam is always one level deep in my org-directory
  (setq org-roam-directory (expand-file-name "~/org/roam"))
  (setq org-id-link-to-org-use-id t)
  (setq org-roam-completion-system 'helm)
  (add-to-list 'display-buffer-alist
               '(("\\*org-roam\\*"
                  (display-buffer-in-direction)
                  (direction . right)
                  (window-width . 0.33)
                  (window-height . fit-window-to-buffer))))
  (setq org-roam-capture-templates
        '(("d" "default" plain "%?"
           :immediate-finish t
           :if-new (file+head "${slug}.org"
                              "#+TITLE: ${title}\n#+hugo_lastmod: Time-stamp: <>\n\n")
           :unnarrowed t)
          ("t" "temp" plain "%?"
           :if-new(file+head "%<%Y%m%d%H%M%S>-${slug}.org"
                             "#+TITLE: ${title}\n#+hugo_lastmod: Time-stamp: <>\n\n")
           :immediate-finish t
           :unnarrowed t)
          ("p" "private" plain "%?"
           :if-new (file+head "${slug}-private.org"
                              "#+TITLE: ${title}\n")
           :immediate-finish t
           :unnarrowed t)))
  (setq org-roam-mode-sections
        (list #'org-roam-backlinks-insert-section
              #'org-roam-reflinks-insert-section
              #'org-roam-unlinked-references-insert-section))
  (org-roam-setup)
  (org-roam-db-autosync-mode)
  (setq org-roam-v2-ack t)
  )
(setq org-id-extra-files (org-roam--list-files org-roam-directory))

(defun my/caldav-sync-perso ()
  "Sync my local calendar in ~/org/calendar.org with my remote calendar"
  (interactive)
  (let ((org-caldav-inbox "~/org/cal_inbox.org")
        (org-caldav-calendar-id "org")
        (org-caldav-url "https://cld.hugocisneros.com/remote.php/dav/calendars/ncp/")
        (org-caldav-files '("~/org/calendar.org")))
    (call-interactively 'org-caldav-sync)))

(setq org-journal-dir "~/org/journal/")
(setq org-journal-enable-encryption t)

(add-hook 'before-save-hook 'time-stamp)

(add-hook 'markdown-mode-hook 'my/buffer-face-mode-variable)

(setq org-return-follows-link t)
