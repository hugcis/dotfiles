tmux splitw -h -p 50
tmux splitw -f
tmux splitw -h -p 50
tmux selectp -t 1
tmux send-keys "jupyter notebook list" Enter
