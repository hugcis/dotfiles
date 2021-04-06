tmux splitw -h -p 50 htop
tmux splitw -f
tmux splitw -h -p 15
tmux send-keys -t 4 "bonsai -i -w 30" Enter
tmux selectp -t 1
