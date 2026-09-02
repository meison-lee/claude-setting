#!/bin/sh
input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd')
dir=$(basename "$cwd")
model=$(echo "$input" | jq -r '.model.display_name')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')
u5=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
u7=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
# resets_at is a Unix epoch in seconds.
r5=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
r7=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')
now=$(date +%s)

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

# progress bar for a percentage: $1 = percentage, $2 = yellow threshold, $3 = red
# threshold. Filled part is colored by pct_color, the remaining track is dim.
# Sub-cell precision comes from the eighth-block characters.
BAR_CELLS=8
bar() {
  p=$(printf '%.0f' "$1")
  [ "$p" -lt 0 ] && p=0
  [ "$p" -gt 100 ] && p=100

  eighths=$((p * BAR_CELLS * 8 / 100))
  full=$((eighths / 8))
  rem=$((eighths % 8))

  filled=""
  i=0
  while [ "$i" -lt "$full" ]; do
    filled="${filled}█"
    i=$((i + 1))
  done
  if [ "$rem" -gt 0 ] && [ "$full" -lt "$BAR_CELLS" ]; then
    case "$rem" in
      1) filled="${filled}▏" ;;
      2) filled="${filled}▎" ;;
      3) filled="${filled}▍" ;;
      4) filled="${filled}▌" ;;
      5) filled="${filled}▋" ;;
      6) filled="${filled}▊" ;;
      7) filled="${filled}▉" ;;
    esac
    full=$((full + 1))
  fi

  track=""
  i="$full"
  while [ "$i" -lt "$BAR_CELLS" ]; do
    track="${track}░"
    i=$((i + 1))
  done

  printf '%s%s%s%s%s%s' "$(pct_color "$p" "$2" "$3")" "$filled" "$RST" "$DIM" "$track" "$RST"
}

# compact time left until the Unix epoch $1: 2d3h / 2h5m / 45m / <1m
countdown() {
  d=$((${1%%.*} - now))
  [ "$d" -lt 0 ] && d=0
  if [ "$d" -ge 86400 ]; then printf '%dd%dh' "$((d / 86400))" "$((d % 86400 / 3600))"
  elif [ "$d" -ge 3600 ]; then printf '%dh%dm' "$((d / 3600))" "$((d % 3600 / 60))"
  elif [ "$d" -ge 60 ]; then printf '%dm' "$((d / 60))"
  else printf '<1m'; fi
}

out="${BOLD}${CYAN}${dir}${RST}"
[ -n "$branch" ] && out="${out} ${MAG}${branch}${RST}"
out="${out}${SEP}${DIM}${model}${RST}"
[ -n "$used" ] && out="${out}${SEP}${DIM}ctx${RST} $(bar "$used" 60 85)"
[ -n "$cost" ] && out="${out}${SEP}${DIM}\$$(printf '%.2f' "$cost")${RST}"
if [ -n "$u5" ] || [ -n "$u7" ]; then
  out="${out}${SEP}"
  if [ -n "$u5" ]; then
    out="${out}${DIM}5h${RST} $(bar "$u5" 70 90)"
    [ -n "$r5" ] && out="${out} ${DIM}$(countdown "$r5")${RST}"
  fi
  [ -n "$u5" ] && [ -n "$u7" ] && out="${out}  "
  if [ -n "$u7" ]; then
    out="${out}${DIM}7d${RST} $(bar "$u7" 70 90)"
    [ -n "$r7" ] && out="${out} ${DIM}$(countdown "$r7")${RST}"
  fi
fi
printf '%s' "$out"
