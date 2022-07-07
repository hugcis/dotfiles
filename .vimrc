execute pathogen#infect()
syntax enable

set background=dark
" colorscheme solarized
filetype plugin indent on
set number
set spelllang=fr,en_gb,en_ca,en_us
inoremap <C-l> <c-g>u<Esc>[s1z=`]a<c-g>u
set expandtab
set autoindent
set smartindent


imap fd <Esc>
vmap fd <Esc>

" Learning mappings
nnoremap <Left> :echoe "Use h"<CR>
nnoremap <Right> :echoe "Use l"<CR>
nnoremap <Up> :echoe "Use k"<CR>
nnoremap <Down> :echoe "Use j"<CR>

" C-h/j/k/l to move between buffers
map <C-h> <C-w>h
map <C-j> <C-w>j
map <C-k> <C-w>k
map <C-l> <C-w>l

" Paste and visual paste improvments {{{
vnoremap <silent> y y`]
vnoremap <silent> p p`]
nnoremap <silent> p p`]

" Space to toggle folds.
nnoremap <Space> za
vnoremap <Space> za
"reload the .vimrc
nmap <silent> <leader>rv :source ~/.vimrc<CR>
"show spaces"
nmap <silent> <leader>s :set nolist!<CR>
"show line numbers"
nmap <silent> <leader>l :set nonu!<CR>
"wrap lines"
nmap <silent> <leader>w :set nowrap!<CR>
"hide hightlight of searches"
nmap <silent> // :nohlsearch<CR>

" =================================================================
" Latex config
let g:tex_flavor='latex'
let g:vimtex_quickfix_mode=0
let g:vimtex_view_method='skim'
let g:vimtex_toc_enabled = 1
set conceallevel=1
let g:tex_conceal='abdmg'

"let g:UltiSnipsExpandTrigger = '<tab>'
"let g:UltiSnipsJumpForwardTrigger = '<tab>'
"let g:UltiSnipsJumpBackwardTrigger = '<s-tab>'

autocmd Filetype tex setlocal textwidth=80 tabstop=2 shiftwidth=2
autocmd FileType tex setlocal spell
autocmd Filetype tex setlocal colorcolumn=+1
highlight ColorColumn ctermbg=lightgrey guibg=lightgrey

" =================================================================
" Airline configuration
let g:airline_theme='molokai'
let g:airline#extensions#tabline#enabled = 1
let g:airline_detect_spell=0

" air-line
let g:airline_powerline_fonts = 1

if !exists('g:airline_symbols')
    let g:airline_symbols = {}
endif

" unicode symbols
let g:airline_left_sep = '»'
let g:airline_left_sep = '▶'
let g:airline_right_sep = '«'
let g:airline_right_sep = '◀'
let g:airline_symbols.linenr = '␊'
let g:airline_symbols.linenr = '␤'
let g:airline_symbols.linenr = '¶'
let g:airline_symbols.branch = '⎇'
let g:airline_symbols.paste = 'ρ'
let g:airline_symbols.paste = 'Þ'
let g:airline_symbols.paste = '∥'
let g:airline_symbols.whitespace = 'Ξ'

" airline symbols
let g:airline_left_sep = ''
let g:airline_left_alt_sep = ''
let g:airline_right_sep = ''
let g:airline_right_alt_sep = ''
let g:airline_symbols.branch = ''
let g:airline_symbols.readonly = ''
let g:airline_symbols.linenr = ''
