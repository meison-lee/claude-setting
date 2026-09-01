# claude-dotfiles

Personal Claude Code configuration, synced across machines.

## What's here

| Path | Purpose |
|---|---|
| `settings.json` | Model, hooks (tab titles, proto auto-format, done-notification), statusline wiring |
| `statusline-command.sh` | Custom statusline: dir, branch, model, ctx %, session cost, 5h/7d usage (health-colored) |
| `tab-title.sh` | Terminal tab title hook: state emoji + repo + task/`/rename` name |
| `skills/` | Personal skills (`/tdd`, `/jira`, `/code-review`, `/research`, …) |
| `install.sh` | Symlinks everything above into `~/.claude/` (re-runnable) |

## New machine setup

```sh
git clone git@github.com:<me>/claude-dotfiles.git ~/claude-dotfiles
~/claude-dotfiles/install.sh
```

Then inside Claude Code, install plugins (per-machine, not synced by files):
`/plugin` → **superpowers**, **gopls-lsp**, **datadog** from `claude-plugins-official`.

## Updating settings

Files in `~/.claude/` are symlinks into this repo, so any edit is already staged here.
After changing settings/skills, commit and push:

```sh
cd ~/claude-dotfiles && git add -A && git commit -m "update settings" && git push
```

On other machines: `git pull` (re-run `install.sh` only if a link broke, e.g. after
Claude Code rewrites `settings.json` in place — `install.sh` detects and fixes that).

## Never put in this repo

Session transcripts (`projects/`), prompt history (`history.jsonl`), `settings.local.json`,
credentials, `tmp/`, caches. Keep the repo **private** regardless.
