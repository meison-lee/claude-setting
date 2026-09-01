---
name: google-doc-content
description: Use when fetching, writing, or editing Google Doc content that the user will paste back into a Google Doc (markdown paste enabled) — adding/editing sections, matching an existing doc's style and language, or reproducing tables and code as markdown.
allowed-tools: Bash, Read, Write, Edit
---

# Google Doc Content (via Markdown)

## Overview

The user keeps documents in Google Docs with **markdown paste enabled**
(Tools → Preferences → "Automatically detect Markdown"). You do **not** edit the
doc directly. Your deliverable is a **Markdown file** the user copies and pastes
into the doc — Google Docs converts `#` headings, `|` tables, and ``` fences into
native formatting on paste.

Two jobs: **read** the existing doc to match its style, and **write** new
markdown that pastes cleanly.

## Workflow

1. **Fetch the current content** to learn the doc's conventions (only if you have
   a URL/ID). Use the export endpoint:
   ```bash
   DOC_ID=...   # the /d/<DOC_ID>/ part of the URL
   curl -sL "https://docs.google.com/document/d/$DOC_ID/export?format=txt" -o doc.txt
   # format=md also exists; txt is reliable but flattens tables to one-cell-per-line.
   ```
   If the response is an HTML login page, the doc isn't link-shared — ask the user
   to set "Anyone with the link – Viewer" or to paste the relevant sections.

2. **Match style AND language.** Read the export and mirror: heading numbering
   (e.g. `4.4.1.`), heading language (zh-TW vs en), table column headers (e.g.
   `Name | Type | M/O/C | Description`), inline labels (`範例`, `API Request`),
   note style (`📌 …`), and cross-reference phrasing (`請參考 6.9. …`). New content
   should be indistinguishable from existing sections.

3. **Write the markdown to a file** (Desktop, or wherever the user says) with the
   Write tool — don't just dump it in chat. Use GFM: `#`/`##`/`###` for the doc's
   heading hierarchy, fenced code blocks with language tags, pipe tables.

4. **Tables — pipe tables with a separator row.** Equal `|` counts per row;
   escape literal `|` as `\|`. For **multi-line cells** (bullet lists, enum
   values), use `<br>` — Google Docs markdown paste renders `<br>` as line breaks
   inside the cell. Raw newlines inside a cell break the table.

5. **Table of contents — never hand-write one.** A Google Docs TOC is an
   auto-generated field built from heading styles; a markdown bullet list pastes
   as dead static text that won't match. Leave a one-line placeholder note telling
   the user to **Insert → Table of contents** (new doc) or click the TOC's refresh
   icon (existing doc). Your only job is correct heading levels so it nests right.

6. **Code examples — match the doc, and verify when you can.**
   - Language: default to whatever the doc already uses. If the doc has none, ask
     which stack the consumers use rather than guessing. Weigh **testability** —
     a language you can run lets you prove the snippet works (see below).
   - If the language is runnable here, write a real round-trip and **execute it**
     (e.g. `go run .`, `node x.js`) before putting it in the doc. Put the *tested*
     code in the doc, not hand-written code you only reasoned about.

7. **Hand off.** Give the file path, and remind the user: pasting converts the
   markdown to native formatting, then Insert/refresh the TOC.

## Quick Reference

| Need | Do |
| --- | --- |
| Get doc content | `curl -sL ".../export?format=txt"` (md also works) |
| Multi-line table cell | `<br>` between lines |
| Literal pipe in cell | `\|` |
| Table of contents | Placeholder note → user inserts/refreshes in Docs |
| Code language | Match the doc; if none, ask; prefer testable |
| Verify code | Actually run it before it goes in the doc |
| Deliverable | A `.md` file to paste, not direct doc edits |

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| Hand-writing the TOC as a markdown list | Leave a note; the user inserts/refreshes the real auto-TOC. |
| Newlines inside a table cell | Use `<br>`; keep the row on one line. |
| Ragged tables (unequal `\|`) | Same delimiter count every row, including the separator. |
| Guessing the code language | Match existing code; otherwise ask the user's stack. |
| Shipping unrun code | Run a round-trip first when the language allows. |
| Assuming export works on private docs | Login-page HTML = not shared; ask the user. |
| Editing the doc "directly" | You can't; produce markdown for the user to paste. |
