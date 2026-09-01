#!/bin/sh
input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd')
dir=$(basename "$cwd")
model=$(echo "$input" | jq -r '.model.display_name')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')
u5=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
u7=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')

# Git branch, if cwd is inside a git repo; blank (no error output) otherwise.
# --no-optional-locks avoids contending with concurrent git operations.
branch=$(git --no-optional-locks -C "$cwd" symbolic-ref --short HEAD 2>/dev/null || git --no-optional-locks -C "$cwd" rev-parse --short HEAD 2>/dev/null)

ESC=$(printf '\033')
RST="${ESC}[0m"
DIM="${ESC}[2m"
BOLD="${ESC}[1m"
CYAN="${ESC}[36m"
MAG="${ESC}[35m"
GRN="${ESC}[32m"
YEL="${ESC}[33m"
RED="${ESC}[31m"
SEP="  ${DIM}|${RST}  "

# green below $2, yellow from $2, red from $3
pct_color() {
  p=$(printf '%.0f' "$1")
  if [ "$p" -ge "$3" ]; then printf '%s' "$RED$BOLD"
  elif [ "$p" -ge "$2" ]; then printf '%s' "$YEL"
  else printf '%s' "$GRN"; fi
}

out="${BOLD}${CYAN}${dir}${RST}"
[ -n "$branch" ] && out="${out} ${MAG}${branch}${RST}"
out="${out}${SEP}${DIM}${model}${RST}"
[ -n "$used" ] && out="${out}${SEP}${DIM}ctx${RST} $(pct_color "$used" 60 85)$(printf '%.0f' "$used")%${RST}"
[ -n "$cost" ] && out="${out}${SEP}${DIM}\$$(printf '%.2f' "$cost")${RST}"
if [ -n "$u5" ] || [ -n "$u7" ]; then
  out="${out}${SEP}"
  [ -n "$u5" ] && out="${out}${DIM}5h${RST} $(pct_color "$u5" 70 90)$(printf '%.0f' "$u5")%${RST}"
  [ -n "$u5" ] && [ -n "$u7" ] && out="${out}  "
  [ -n "$u7" ] && out="${out}${DIM}7d${RST} $(pct_color "$u7" 70 90)$(printf '%.0f' "$u7")%${RST}"
fi
printf '%s' "$out"
