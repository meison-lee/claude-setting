---
name: fortify-triage-to-jira
description: Use when you have reviewed Fortify triage sheets (the .xlsx from the fortify-report skill, with the "Status / Notes" column filled in by a human) and need to compile the items that will be fixed into a Jira ticket, grouped by project, with links back to the report. Covers extracting actionable findings from reviewer notes and writing/updating the Jira Description.
---

# Fortify Triage Sheet → Jira Ticket Description

## Overview

Downstream of the `fortify-report` skill. That skill produces one `.xlsx`
triage sheet per repo/scan; a human then reviews each finding and fills the
**`Status / Notes`** column. This skill turns those *reviewed* sheets into a
single Jira ticket **Description** (grouped by project) listing what will be
fixed, plus a back-reference so a reviewer can find each finding's original
risk description in the report.

**Core principle: the human's `Status / Notes` text is the source of truth for
whether an item gets fixed — NOT the drafted `Suggested Decision` column.** The
reviewer routinely keeps `Suggested Decision = Needs Review` while writing
"不修改" in the note, or keeps `Won't Fix (Accept Risk)` while writing
"可修，補上版本". Read the note, not the decision.

## Inputs

- One or more **reviewed** triage sheets (e.g. `auth-2606.xlsx`,
  `gateway-2605.xlsx`). The same project may have multiple scan months.
- The target Jira ticket key (e.g. `GAMAPASS-3342`).

If the sheets are unreviewed (empty `Status / Notes`), stop — there is nothing
to compile. Ask the reviewer to fill notes first.

## Workflow

### 1. Collect candidates deterministically

```bash
python3 ~/.claude/skills/fortify-triage-to-jira/collect_actionable.py \
    "auth-2606.xlsx" "gateway-2606.xlsx" "backpack-2606.xlsx" [older scans...]
```

The script excludes only rows whose note clearly says **won't-fix** (see
`NO_FIX` list in the script) and prints every remaining row as a **candidate**
with its note, grouped by project. It is intentionally conservative — it never
uses inclusion keywords, because false-positive notes contain fix-verbs too
("可以**改**但風險不高", "故無…風險"). Add new won't-fix phrasings to `NO_FIX`
as they appear.

### 2. Apply judgment to each candidate (read the note)

| Note says… | Action |
|---|---|
| 需修正 / 需修復 / 可修，補上… / 改用指定版本 / rotate 並移除 / 開單修補 | **Include** (will fix) |
| 再評估是否… / 可能需要… | Include, tag **【待評估】** |
| 可以改但風險不高 / 風險比較低…（無修正字樣） | Borderline — surface to the user, don't silently include |
| 不修改 / 不處理 / 無風險 / 誤報 / 只是…comment/測試 | Exclude → put in the "暫不修改" section |

**Same location, conflicting notes across source-traces:** if *any* trace on a
sink says 需修正, **include** the location. The fix (e.g. masking in one
function) covers every call site regardless. (This is how `client.go:355` gets
included even though one of its rows said "不修改".)

### 3. Group + pick canonical scan

Group by project. When a project has multiple scans, use the **latest**
(highest YYMM) as the canonical `No.`, and cross-reference the older scan's
`No.` in parentheses. Confirm no fix-item unique to an older scan is dropped.

### 4. Compose the Description (mind the format gotchas)

The Atlassian MCP `jira_update_issue` **description** field takes Markdown but:
- **`**bold**` gets escaped to literal `\*\*`** — do NOT use bold.
- **Nested/indented bullets flatten** to one level.
- `##` headings, `-` single-level bullets, and `` `backticks` `` render fine.

So format each finding as **one single-level bullet, one line**, fields
separated by `｜`:

```
## 🟦 gama-auth ｜ 報告 auth-2606.xlsx

- <問題> ｜ `<location>` ｜ 動作:<what to do> ｜ 報告對應 #<No> · <Category>
```

Start the Description with a **trace-back header** so reviewers can find the
original risk text:

> 如何回報告查 risk 描述:開對應的 `xxx-<scan>.xlsx` → 用 `No.` 欄篩選到該筆 →
> 看 **Abstract** 欄(Fortify 原始描述)+ **Reason (draft)** / **Status / Notes** 欄。

End with a **「暫不修改」section** listing the consciously-excluded items (with
their #No), so reviewers see they were triaged, not forgotten.

### 5. Write and VERIFY

- New/empty ticket → `jira_update_issue` on the `description` field.
  (A `jira_add_comment` renders Markdown but **flattens tables**; the
  description path **escapes `**`**. Either way, avoid tables and bold.)
- **Always re-fetch and verify** with `jira_get_issue` (`fields=description`):
  confirm no `\*\*` escaping and headings/bullets survived. Fix and re-write if
  the format broke.

## Quick Reference

| Step | Tool / command |
|---|---|
| Collect candidates | `collect_actionable.py *.xlsx` |
| Read a note's intent | the `Status / Notes` column only |
| Write description | `jira_update_issue` `fields={"description": "..."}` |
| Verify render | `jira_get_issue` `fields=description` |
| Remove a stray comment | no delete tool — `jira_edit_comment` to a tombstone line |

## Common Mistakes

- **Trusting `Suggested Decision` instead of the note.** The note overrides it.
- **Using inclusion keywords to find fixes.** False positives contain "改"/"fix".
  Exclude won't-fix notes; treat the rest as candidates.
- **Using `**bold**` or Markdown tables in the Jira description.** They break —
  headings + `｜`-separated bullets only. Verify by re-fetching.
- **Dropping a location because one of its duplicate rows said 不修改.** If any
  trace says 需修正, keep it.
- **Omitting the trace-back header / #No.** Without the report filename + `No.`,
  reviewers can't find the original risk description.
- **Silently including borderline items** ("風險不高") — surface them for a
  decision instead.
