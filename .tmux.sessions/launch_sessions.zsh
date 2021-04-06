#!/bin/zsh                                                                                                   

for fullpath in ~/.tmux.sessions.local/*
do
    file="${fullpath##*/}"
    echo "Found session configuration $file"
    if [ -f $fullpath ] && [ ${file: -3} = ".sh" ]; then
        SESSIONNAME="${file: :-3}"
        tmux has-session -t $SESSIONNAME &> /dev/null
        if [ $? != 0 ]; then
                tmux new-session -s $SESSIONNAME -n script -d
                tmux send-keys -t $SESSIONNAME "$fullpath" Enter clear Enter
        fi
    fi
done

