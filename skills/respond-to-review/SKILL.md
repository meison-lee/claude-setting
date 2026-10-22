---
name: respond-to-review
description: Use when a reviewer has commented on our MR (GitLab, gama-* repos) — audit each point, fix and push, reply on the review thread, and tag the reviewer in the MR's Google Chat thread.
---

# Respond to review

A review is answered when every point has a verdict (fixed, reply-only, or the user's call), the fixes are pushed, the
reviewer has a point-by-point reply on their thread, and, when the user asked for it, the reviewer is tagged in Chat.

## Steps

### 1. Collect

- `git fetch --prune` first; review state on the remote is the truth, local worktrees go stale.
- For every MR of the ticket (all repos), list the non-system notes by anyone other than the user, with discussion id,
  `position` (file:line) and the commit the reviewer read (they often name it, e.g. "以 `fc13cb6` 為準").
- Pending GitLab reviews are invisible to the API until the reviewer submits them. When the user says a review exists
  and the API shows none, say so; never claim a review you did not read.
- Done when every reviewer note on every MR is listed with its discussion id.

### 2. Audit

- Check each point against the code at the reviewed commit, then at the branch head. Verdicts:
  **fix** (real defect, doc that contradicts code, cheap readability win), **reply-only** (works as designed; give the
  reason), **ask** (product or spec decision the code cannot settle).
- A point that is right in a way the reviewer did not see (e.g. it reaches a 400 anyway) is still a fix when it changes
  behaviour versus main.
- Done when every point has a verdict backed by a `file:line` you read.

### 3. Fix

- Work in the branch's own worktree; follow the repo's CLAUDE.md for commit suffix, lint gate and tests. A regression
  test for each behaviour fix, shown failing without the fix.
- Before pushing: confirm auto-merge is off and the remote head is the one you built on; push fast-forward only.
- Pushing resets approvals in gama-auth and gama-api-gateway: say so in the report.
- Done when the push landed and lint and tests are green.

### 4. Reply on the MR

- Reply inside the reviewer's discussion (`POST .../discussions/<id>/notes`), in the reviewer's language, mirroring
  their headings: each point gets fixed + commit hash + test name, or the reason it stays.
- Done when the note is posted and its id is noted for step 5.

### 5. Tag the reviewer in Chat (only when the user asked for it in this request)

Run from the MR's repo checkout (its `.env` holds the webhook and the `GCHAT_USER_<gitlab username>` table):

```
python3 -I ~/.claude/skills/respond-to-review/scripts/gchat_mention.py --mr <iid> --user <gitlab username> \
  --text "<repo> !<iid> 的 review 已逐點回覆…：<note link>"
```

It is a dry run until `--send`. Read its `tag` line, then apply the **identity check** below; send only when sure.
A Chat post cannot be recalled: on a send failure, look at the thread before any second attempt.

### 6. Watch (optional)

When the user wants to merge after approval, run a background poll that exits on: an approval, a new non-system note
from someone other than the user, or the MR leaving `opened`. On a new note, go back to step 1.

## Identity check

Tagging the wrong person is the one unrecoverable mistake here, so the bar is **sure**, and anything short of it is a
question to the user (AskUserQuestion, naming the GitLab username, GitLab name and the Chat ID you would use).

Sure means all of:

- The person to tag is the **author of the note** you are answering (`author.username`), not someone named in it.
- `.env` maps exactly that username (the script exits 3 "NOT SURE" otherwise: missing key, malformed ID, or one ID
  shared by two usernames).
- The script's GitLab name is the person you expect: two people can share a first name (`jimmylu` 呂啟銘 vs
  `jimmychen` 陳在霆), so compare the full name, never the first word.

Ask instead of sending when any fails, and for an unmapped user offer the verified lookup: the "New Merge Request" card
on an MR **they authored** mentions them; read its `USER_MENTION` with the Chat API
(`spaces/<space>/messages`, `filter=thread.name = "<their gchat-thread>"`, token from
`gcloud auth application-default print-access-token`, `x-goog-user-project` from `~/.claude/gchat-bridge/config.json`).
Add the new `GCHAT_USER_<username>=users/<id>` line to `.env` in both gama-auth and gama-api-gateway only after the
user confirms. A display-name match alone is a guess, never a mapping.
