#!/bin/sh
# Terminal tab title: "<state> <repo> · <task>"  for the current Claude Code session.
# $1 = state emoji (🔵 working / 🔧 tool running / 🟢 done). Hook JSON arrives on stdin.
# A manual /rename (custom-title record in the session transcript) takes priority
# over the auto task summary captured from the latest prompt.
input=$(cat)
sid=$(printf '%s' "$input" | jq -r '.session_id // "unknown"')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
repo=$(basename "${cwd:-$PWD}")
dir="$HOME/.claude/tmp/tab-titles"
mkdir -p "$dir"

# UserPromptSubmit carries .prompt -> remember it as this session's auto task
task=$(printf '%s' "$input" | jq -r '.prompt // empty | split("\n")[0] | gsub("\\s+"; " ") | .[0:48]')
if [ -n "$task" ]; then
  printf '%s' "$task" > "$dir/$sid"
else
  task=$(cat "$dir/$sid" 2>/dev/null)
fi

# /rename wins: latest custom-title record in the session transcript
proj=$(printf '%s' "${cwd:-$PWD}" | sed 's/[^A-Za-z0-9]/-/g')
tf="$HOME/.claude/projects/$proj/$sid.jsonl"
if [ -f "$tf" ]; then
  pin=$(command grep '"type":"custom-title"' "$tf" 2>/dev/null | tail -1 | jq -r '.customTitle // empty | .[0:48]')
  [ -n "$pin" ] && task="$pin"
fi

tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')
title="${1:-🔵} $repo"
[ -n "$task" ] && title="$title · $task"
[ -n "$tool" ] && title="$title [$tool]"

if [ -n "$TAB_TITLE_DEBUG" ]; then printf '%s\n' "$title"; fi
t=$(ps -o tty= -p $$ | tr -d ' ')
[ -n "$t" ] && [ "$t" != "??" ] && printf '\033]0;%s\007' "$title" > "/dev/$t" 2>/dev/null
find "$dir" -type f -mtime +7 -delete 2>/dev/null
exit 0
