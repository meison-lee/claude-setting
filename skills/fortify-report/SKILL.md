---
name: fortify-report
description: Use when the user has a Fortify SCA "Developer Workbook" PDF report and wants it turned into an Excel (.xlsx) triage sheet — extracts every finding (risk level, category, location, OWASP, abstract) and drafts a suggested decision + rationale for whether/why each will (not) be fixed.
---

# Fortify Report → Excel Triage Sheet

## Overview

Turns a Fortify SCA **Developer Workbook** PDF into a single-sheet Excel
workbook. The sheet has a metadata header block (project, commit, Fortify
version, scan date, LOC, severity counts — the attributes that define what the
scan covered) followed by one row per finding. Claude drafts a **Suggested
Decision** and **Reason** per finding for the user/security team to review.

Two Python scripts bracket a Claude reasoning step:

```
extract.py <pdf>  ->  <pdf>.findings.json   (deterministic parse + self-check)
        Claude adds "decision" + "reason" per finding -> enriched.json
outname.py <findings.json>  ->  <short>-<YYMM>   (filename stem from commit date)
build_xlsx.py <enriched.json> -o <out.xlsx>  (formatted single sheet)
```

## Output filename

The workbook is named `<short-project>-<YYMM>.xlsx`, e.g. `gateway-2606.xlsx`,
`auth-2606.xlsx`, `sender-2606.xlsx`, `backpack-2606.xlsx`.

- **short-project** = the last `-` segment of the report's project name
  (`gama-api-gateway` -> `gateway`, `gama-auth` -> `auth`, etc.).
- **YYMM** = the month the commit was **implemented**, read from the commit's
  **author date** — NOT the report generation time. Reports can be
  regenerated/back-filled later, so the scan date is unreliable for this.

`outname.py` resolves the month from `meta.commit` in this order:
1. local git repo at `<base>/<project>` (base defaults to the parent of the
   current repo, then `~/Gama`; override with `--base` or `$GAMA_REPO_BASE`),
2. GitLab via `glab` (project path guessed as `gama-pass/backend/<project>`),
3. **give up and exit non-zero** — when that happens, **STOP AND ASK the user**
   for the month (`YYMM`) and re-run with `outname.py ... --month YYMM`. NEVER
   silently fall back to the report's scan date.

Deterministic extraction keeps counts and locations accurate; Claude only does
the judgement (the triage rationale).

## Dependencies

`pypdf` and `openpyxl`. If either import fails:

```bash
python3 -m pip install --user pypdf openpyxl
```

## Workflow

1. **Get the PDF path** from the user.

2. **Extract** — run from the scratchpad dir:
   ```bash
   python3 ~/.claude/skills/fortify-report/extract.py "<report.pdf>" -o findings.json
   ```
   The script prints `Parsed N findings (report total: M)` and **exits non-zero
   with warnings if N != M** or if per-severity counts don't match the report's
   own summary. **Never ignore a mismatch** — it means the parser missed or
   split findings. Inspect the PDF text and adjust before continuing.

3. **Draft triage** — read `findings.json` and add two fields to each finding:
   - `decision`: one of `Fix`, `Won't Fix (False Positive)`,
     `Won't Fix (Accept Risk)`, `Needs Review` (adjust labels to the team's
     convention if the user has one).
   - `reason`: a concise, honest rationale. Base it on the finding's abstract,
     source/sink, and knowledge of the codebase. Mark clear false positives
     (e.g. `json.Marshal` flagged as injection — Go escapes safely; TLS-terminated
     -at-ingress for plain HTTP; deprecated no-op TLS flags) and flag anything
     needing code inspection (hardcoded-credential reports, redirect allowlist
     checks) as `Needs Review` rather than guessing.

     Save as `enriched.json`. **Confirm the count still equals the report total
     before building.**

4. **Derive the filename stem** from the commit's implementation month:
   ```bash
   stem=$(python3 ~/.claude/skills/fortify-report/outname.py enriched.json)
   ```
   If this exits non-zero (month unresolved), **STOP AND ASK the user** for the
   month, then re-run with `--month YYMM`. Do not proceed with a guessed date.

5. **Build the Excel** (output goes next to the source PDF):
   ```bash
   python3 ~/.claude/skills/fortify-report/build_xlsx.py enriched.json \
       -o "<pdf_dir>/$stem.xlsx"
   ```
   Risk-level cells are color-coded (Critical/High/Medium/Low), rows are sorted
   by severity, the header row is frozen, and an auto-filter is applied.

6. **Report** the output path and remind the user the `decision`/`reason`
   columns are **drafts to review**; the `Status / Notes` column is left blank
   for their team.

## Notes

- The finding anchor is `<location>, line <N> (<Category>)` immediately followed
  by `Fortify Priority: <Level>`. The same sink can appear multiple times with
  different source traces — Fortify counts each as a separate issue, so the
  parser does **not** deduplicate by location; the summary-count self-check is
  the safety net.
- The commit hash is read from the PDF filename (`<project>-<sha>.pdf`). If the
  filename has no hash, `meta.commit` is null — ask the user to supply it.
- `extract.py` strips the recurring page footer so it can't bleed into a
  finding's abstract/OWASP field.
