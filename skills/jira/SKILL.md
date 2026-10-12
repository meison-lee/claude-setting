---
name: jira
description: Use when reading a Jira ticket by key (requirements, AC, comments), when creating a new ticket / rewriting a ticket description, or when filling a Bug's Root Cause / Solution after its fix, for the GAMAPASS project
allowed-tools: Bash, Write, Read, WebFetch
---

# Jira (GAMAPASS)

`JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_BASE_URL` are exported in `~/.zshrc`, which
**non-interactive shells do not source** — `build_ticket.py` loads them from
`~/.zshrc` by itself, but any raw shell command using `$JIRA_*` must be prefixed
with `source ~/.zshrc >/dev/null 2>&1;`. Project key: `GAMAPASS`. Default issue
type: `Task`.

Three jobs: **read a ticket** (below), **write a ticket** (the house structure —
that section is the contract, not a suggestion), and **close out a Bug** by filling its
Root Cause / Solution.

---

## Reading a ticket

`$ARGUMENTS` is the ticket key. **If it is empty or is not a `[A-Z]+-[0-9]+` key,
stop and ask which ticket** — do not paste prose into the URL.

```bash
source ~/.zshrc >/dev/null 2>&1
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/issue/$ARGUMENTS?fields=summary,description,status,priority,issuetype,labels,components,assignee,reporter,comment,customfield_10014" \
  | python3 -m json.tool
```

Present as:

```
## [TICKET-ID] Title
**Status:** ... | **Priority:** ... | **Type:** ...
**Assignee:** ... | **Reporter:** ...
**Labels:** ... | **Components:** ...

### Description
(ADF → markdown)

### Acceptance Criteria
(extract if present, else note it is missing)

### Comments (latest 5)
```

Descriptions are Atlassian Document Format (nested `type`/`content` nodes).
Recurse and convert: `heading` → `##`/`###`, `paragraph` → text, `bulletList` /
`orderedList` → markdown lists, **`taskList`/`taskItem` → `- [ ]` / `- [x]`
(read `attrs.state`; `DONE` means checked)**, `codeBlock` → fenced block,
`text` marks (`code`/`strong`/`em`/`link`) → backticks/bold/italic/link,
`table` → markdown table, `mediaSingle`/`mediaGroup` → `[attachment]`.

---

## Writing a ticket — the house structure

Tickets are read by PM, QA, DevOps and other engineers, not just the author.
Every ticket description consists of exactly these sections, in this order:

| Section | Contains | Length |
|---|---|---|
| `【背景／目的】` | **Required.** What is happening and why it is worth doing, in language a non-engineer can follow, then the goal in one sentence. For a Bug: 預期行為 vs 實際行為 + 重現步驟. | 2–4 短段落 |
| `【待確認事項】` | **Optional — only when blocked on someone else's answer.** One lead-in line naming who should answer, then a `tasks` checklist of just the decisions that actually block the work. | ≤ 3 項 |
| `【實作方式】` | **Required.** The approach as short bullets — one bullet per change, saying what changes and what it achieves. | 2–4 bullets |
| `【影響範圍】` | **Required.** Who and what is affected: services/environments, DB & deployment risk, compatibility, what QA should verify. | 3–5 bullets |

**A ticket is a decision aid, not an engineering report.** Aim for something a
PM can read in under a minute. Keep OUT of the ticket (it belongs in the MR, the
code, or the chat):

- 觸及檔案清單 / `path:line` refs — the implementer finds these from the code
- alternatives considered and why they were rejected
- `EXPLAIN` output, benchmark SQL, verification commands, 驗收標準 checklists
- the reasoning chain behind a conclusion — state the conclusion

No other top-level sections. If a section genuinely needs internal structure,
use one sub-heading (`h`) — but needing sub-headings usually means it is too long.

### Language: 繁體中文

Prose, section titles, list items and headings are **Traditional Chinese**.
Keep verbatim in English, never translated:

- identifiers, functions, types — `created_time`, `ListByCreatedTimeBetween`
- file paths and `path:line` refs — `internal/repository/user.go:978`
- SQL, code blocks, commands, env vars, error codes, ticket keys, toggle names

Summary line follows the existing convention: `[BE] <繁中或英文簡述>`.

### Workflow

1. Write a ticket JSON to the scratchpad (schema: the docstring at the top of
   `build_ticket.py`).
2. **Dry-run and read the preview** before anything is sent:
   ```bash
   python3 ~/.claude/skills/jira/build_ticket.py ticket.json --dry-run
   ```
3. Send it:
   ```bash
   python3 ~/.claude/skills/jira/build_ticket.py ticket.json
   ```
   No `"ticket"` key → creates (POST, reporter = current user). With
   `"ticket": "GAMAPASS-1234"` → **overwrites that ticket's description** (PUT).
4. Report the key and URL.

Before updating an existing ticket, fetch its current description first and
confirm with the user — PUT replaces it, and there is no undo.

### Block shorthand

Inside each section, blocks are: `{"p":...}` paragraph, `{"h":...}` sub-heading,
`{"ul":[...]}` / `{"ol":[...]}` lists, `{"code":..., "lang":...}` code block,
`{"tasks":[...]}` checklist, `{"table": {"headers":[...], "rows":[[...]]}}` table
(`headers` optional; a cell is a string or a list of strings), `{"panel":...,
"type":"warning"}` callout (type ∈ info/note/success/warning/error), `{"quote":...}`
blockquote, `{"rule": true}` divider. Inline `` `code` ``, `**bold**` and
`[text](https://url)` links work in any string. `"pending"` accepts a bare array
of strings as checklist shorthand.

Tables/panels are available but the house structure still applies — reach for a
table only when tabular data genuinely reads better as a grid (a small mapping,
a comparison); prose and bullets remain the default for a decision aid.

```json
{
  "project": "GAMAPASS",
  "issuetype": "Task",
  "summary": "[BE] 每日同步 cronjob 查詢優化",
  "background": [
    {"p": "每日 cronjob `process_bf_openid_mapping_daily` 執行時間過長。"},
    {"ul": ["目標:讓查詢時間不隨 `users` 成長而惡化"]}
  ],
  "pending": ["請 PM 確認此 cronjob 是否仍在使用中"],
  "implementation": [
    {"h": "1. 補上索引"},
    {"code": "CREATE INDEX \"idx_users_created_time\" ON \"users\" (\"created_time\");", "lang": "sql"}
  ],
  "impact": [
    {"p": "僅影響 gama-auth 的每日 cronjob,不影響線上 API。"}
  ]
}
```

## Closing out a Bug — Root Cause / Solution

Every Bug ticket you fix ends with its **Root Cause** (`customfield_10286`) and
**Solution** (`customfield_10283`) filled, once the fix MR is open. Done when both
fields read back filled and the description is byte-for-byte what it was.

**The description belongs to the reporter** — usually QA or PM opened the ticket. These
two fields are where the engineer's account goes. `build_ticket.py`'s bug-fields mode
PUTs only them, refuses a spec that also carries description sections, and refuses to
replace a filled field unless you pass `--overwrite` (read what is there first).

```json
{
  "ticket": "GAMAPASS-3797",
  "root_cause": [<block>, ...],
  "solution":   [<block>, ...]
}
```

Dry-run, read the preview, send — same as the description workflow.

### Write for QA

The readers are QA and PM: they use these fields to understand what went wrong, to
decide what to retest, and to explain it to others. Write the way you would explain it
to a QA colleague at their desk — screens, buttons, what the user sees, in 繁體中文.

- **Root Cause** — two short paragraphs or bullets:
  - 現象：what QA saw, in screen terms.
  - 原因：why, in product terms. Name a technical term only when it is the actual
    cause, and then say what it means in one clause.
- **Solution** — bullets:
  - 修正內容：what behaves differently now.
  - 影響範圍：what else this touches, and what it deliberately does not.
  - 驗證方式：steps QA can perform on screen or via the backstage, with the expected
    result.
  - the MR link (`gama-auth !973`) — that is where function names, SQL, file paths and
    test names live.

Example (GAMAPASS-3797):

```
Root Cause
- 現象：後台「條款管理」的四個頁籤順序與規格不同，「帳號刪除暨服務終止同意書」排在第一個。
- 原因：頁籤順序由後端決定，而後端當初沒有替條款設定顯示順序，系統就依條款的英文代號
  按字母排序（account_deletion 開頭是 a），排成「帳號刪除 → 個人化行銷 → 隱私權 → 會員服務」。

Solution
- 修正內容：後端替每種條款加上固定的顯示順序，依 QA 規格（GAMAPASS-1293 US01）排列：
  隱私權政策 → 會員服務條款 → 個人化行銷優惠授權 → 帳號刪除暨服務終止同意書。
- 影響範圍：只影響後台條款管理的頁籤順序；前台、官網與各條款的內容、版本都不受影響，前端不需修改。
- 驗證方式：進入後台「基礎設定管理 > 條款管理」，頁籤由左到右應為上述順序，點各頁籤內容正確。
- 修正 MR：gama-auth !973
```

## Common mistakes

- **Dumping the whole investigation into the ticket.** Everything you found while
  diagnosing does not belong there — the ticket carries the conclusion and the
  decision to be made. Depth goes in the conversation or the MR.
- **Inflating 【待確認事項】.** Only genuine blockers. "Nice to know" questions
  (volume estimates, historical backfill, downstream consumers) are not blockers
  and dilute the ones that are — ask those in chat instead.
- **Inventing content to fill a section.** If 影響範圍 is genuinely unknown, ask
  or write what is known; an invented list is worse than an honest gap.
- **Writing 【實作方式】 as settled work while the ticket is still blocked** —
  prefix it with 「以下只在確認…後才進行」.
- **Skipping the dry-run**, or PUT-ing over a description without reading the
  existing one first.
- **Translating identifiers into Chinese**, or conversely writing whole
  paragraphs in English because the source material was English.
- **Adding extra top-level sections** (背景, 調查結果, 驗收標準, 部署注意 …).
  Fold them into the three: goal → 背景／目的, approach → 實作方式,
  deployment/risk/QA → 影響範圍.
