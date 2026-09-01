#!/bin/sh
# Symlink Claude Code config from this repo into ~/.claude/.
# Re-runnable: fixes broken/replaced links; backs up real files it would shadow.
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_DIR"

link() {
  src="$REPO/$1"
  dst="$CLAUDE_DIR/$1"
  # already correct
  [ "$(readlink "$dst" 2>/dev/null)" = "$src" ] && { echo "ok      $1"; return; }
  # a real file/dir is in the way: back it up
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    mv "$dst" "$dst.pre-dotfiles.$(date +%Y%m%d%H%M%S)"
    echo "backup  $1 -> $1.pre-dotfiles.*"
  fi
  ln -sfn "$src" "$dst"
  echo "linked  $1"
}

link settings.json
link statusline-command.sh
link tab-title.sh
link skills

chmod +x "$REPO/statusline-command.sh" "$REPO/tab-title.sh"

echo
echo "Done. Plugins are installed per-machine — in Claude Code run:"
echo "  /plugin  ->  install superpowers, gopls-lsp, datadog (claude-plugins-official)"
