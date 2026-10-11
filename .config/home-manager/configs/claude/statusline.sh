#!/bin/bash
input=$(cat)
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
dir=$(basename "$cwd")

# Git branch + clean/dirty
git_info=""
if git -C "$cwd" rev-parse --git-dir > /dev/null 2>&1; then
  branch=$(git -C "$cwd" --no-optional-locks rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ -n "$branch" ]; then
    if ! git -C "$cwd" --no-optional-locks diff --quiet 2>/dev/null || \
       ! git -C "$cwd" --no-optional-locks diff --cached --quiet 2>/dev/null; then
      si="●"
    else
      si="✓"
    fi
    git_info=" git:($branch $si)"
  fi
fi

# Context usage progress bar
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
ctx=""
ctx_color=""
if [ -n "$used_pct" ]; then
  pct=$(printf '%.0f' "$used_pct")
  bar_width=20
  filled=$(( pct * bar_width / 100 ))
  empty=$(( bar_width - filled ))
  bar=""
  for ((i=0; i<filled; i++)); do bar="${bar}█"; done
  for ((i=0; i<empty; i++)); do bar="${bar}░"; done
  if [ "$pct" -ge 80 ]; then
    ctx=" [${bar} ${pct}%!]"
    ctx_color="\033[31m"
  elif [ "$pct" -ge 50 ]; then
    ctx=" [${bar} ${pct}%]"
    ctx_color="\033[33m"
  else
    ctx=" [${bar} ${pct}%]"
    ctx_color="\033[32m"
  fi
fi

# Vim mode
vim=$(echo "$input" | jq -r '.vim.mode // empty')
vim_info=""
if [ -n "$vim" ]; then
  if [ "$vim" = "NORMAL" ]; then vim_info=" [N]"; else vim_info=" [I]"; fi
fi

# ── Claude API usage (cached, refreshed every 5 minutes in background) ──────
USAGE_CACHE="$HOME/.claude/usage-cache.json"
USAGE_LOCK="$HOME/.claude/usage-cache.lock"
CACHE_TTL=300   # seconds between background refreshes

_refresh_usage_cache() {
  # Acquire a PID-based lock so stale locks from dead processes are cleared
  if [ -f "$USAGE_LOCK" ]; then
    old_pid=$(cat "$USAGE_LOCK" 2>/dev/null)
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
      return  # another refresh is genuinely running
    fi
    rm -f "$USAGE_LOCK"  # stale lock from a dead process
  fi
  echo $$ > "$USAGE_LOCK" 2>/dev/null || return
  trap 'rm -f "$USAGE_LOCK"' EXIT

  local creds token data
  creds=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null) || { rm -f "$USAGE_LOCK"; return; }
  token=$(echo "$creds" | jq -r '.claudeAiOauth.accessToken' 2>/dev/null)          || { rm -f "$USAGE_LOCK"; return; }
  [ -z "$token" ] && { rm -f "$USAGE_LOCK"; return; }

  data=$(curl -s --max-time 10 "https://api.anthropic.com/api/oauth/usage" \
      -H "Authorization: Bearer $token" \
      -H "anthropic-beta: oauth-2025-04-20" \
      -H "User-Agent: claude-code/2.0.32" 2>/dev/null)

  # Only write if we got a valid JSON object with a seven_day field and no error field
  if echo "$data" | jq -e 'type == "object" and has("seven_day") and (.error == null)' > /dev/null 2>&1; then
    echo "$data" > "$USAGE_CACHE"
    touch "$USAGE_CACHE"
  fi
  rm -f "$USAGE_LOCK"
}

# Trigger background refresh if cache is missing or stale
if [ ! -f "$USAGE_CACHE" ] || \
   [ $(( $(date +%s) - $(date -r "$USAGE_CACHE" +%s 2>/dev/null || echo 0) )) -gt $CACHE_TTL ]; then
  _refresh_usage_cache &
  disown 2>/dev/null || true
fi

# Build usage display from cache (if available)
usage_info=""
if [ -f "$USAGE_CACHE" ]; then
  raw=$(cat "$USAGE_CACHE")

  five_pct=$(echo "$raw"   | jq -r '.five_hour.utilization // empty')
  five_reset=$(echo "$raw" | jq -r '.five_hour.resets_at  // empty')
  seven_pct=$(echo "$raw"  | jq -r '.seven_day.utilization // empty')
  seven_reset=$(echo "$raw" | jq -r '.seven_day.resets_at  // empty')

  if [ -n "$five_pct" ] && [ -n "$seven_pct" ]; then
    # Round to integers
    five_int=$(printf '%.0f' "$five_pct")
    seven_int=$(printf '%.0f' "$seven_pct")

    # ── time remaining until 5h window resets ────────────────────────────────
    five_reset_label=""
    if [ -n "$five_reset" ]; then
      now_epoch=$(date +%s)
      five_reset_epoch=$(python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('${five_reset}').timestamp()))" 2>/dev/null || echo 0)
      if [ "$five_reset_epoch" -gt "$now_epoch" ]; then
        secs_left=$(( five_reset_epoch - now_epoch ))
        hrs_left=$(( secs_left / 3600 ))
        mins_left=$(( (secs_left % 3600) / 60 ))
        if [ "$hrs_left" -gt 0 ]; then
          five_reset_label=" (${hrs_left}h${mins_left}m)"
        else
          five_reset_label=" (${mins_left}m)"
        fi
      else
        five_reset_label=" (now)"
      fi
    fi

    # ── weekly pace calculation ──────────────────────────────────────────────
    pace_label=""
    if [ -n "$seven_reset" ]; then
      now_epoch=$(date +%s)
      reset_epoch=$(python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('${seven_reset}').timestamp()))" 2>/dev/null || echo 0)
      if [ "$reset_epoch" -gt 0 ]; then
        start_epoch=$(( reset_epoch - 604800 ))
        elapsed=$(( now_epoch - start_epoch ))
        # time_pct as integer (0-100)
        time_pct=$(( elapsed * 100 / 604800 ))
        [ $time_pct -lt 0 ]   && time_pct=0
        [ $time_pct -gt 100 ] && time_pct=100

        diff=$(( seven_int - time_pct ))

        if [ $diff -gt 5 ]; then
          pace_label=" 🔥+$diff%"     # ahead of pace
        elif [ $diff -lt -5 ]; then
          neg_diff=$(( diff * -1 ))
          pace_label=" ❄️-${neg_diff}%"  # behind pace (headroom)
        else
          pace_label=" ✅"           # on track
        fi
      fi
    fi

    # ── mini bar for weekly usage vs linear pace ─────────────────────────────
    bar_w=10
    filled_w=$(( seven_int * bar_w / 100 ))
    [ $filled_w -gt $bar_w ] && filled_w=$bar_w
    empty_w=$(( bar_w - filled_w ))
    wbar=""
    for ((i=0; i<filled_w; i++)); do wbar="${wbar}▪"; done
    for ((i=0; i<empty_w;  i++)); do wbar="${wbar}·"; done

    # Color: red >= 80, yellow >= 50, green otherwise
    if [ "$seven_int" -ge 80 ]; then
      wcolor="\033[31m"
    elif [ "$seven_int" -ge 50 ]; then
      wcolor="\033[33m"
    else
      wcolor="\033[32m"
    fi

    # Pace color: red = ahead (burning fast), cyan = behind (headroom), default = on track
    if [ $diff -gt 5 ] 2>/dev/null; then
      pcolor="\033[31m"
    elif [ $diff -lt -5 ] 2>/dev/null; then
      pcolor="\033[36m"
    else
      pcolor="\033[0m"
    fi

    usage_info=$(printf " | 5h:\033[33m%d%%%s\033[0m wk:${wcolor}%s %d%%${pcolor}%s\033[0m" \
      "$five_int" "$five_reset_label" "$wbar" "$seven_int" "$pace_label")
  fi
fi

printf "📁 \033[36m%s\033[0m\033[33m%s\033[0m${ctx_color}%s\033[0m\033[35m%s\033[0m%s" \
  "$dir" "$git_info" "$ctx" "$vim_info" "$usage_info"
