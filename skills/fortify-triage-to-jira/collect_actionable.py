#!/usr/bin/env python3
"""
Collect actionable Fortify findings from *reviewed* triage sheets (.xlsx) and
emit them grouped by project, ready to compose a Jira ticket Description.

The reviewed sheet is the fortify-report output AFTER a human filled in the
`Status / Notes` column. The human's note — NOT the drafted `Suggested Decision`
— is the source of truth for whether an item will be fixed.

This script is deliberately CONSERVATIVE: it excludes only rows whose note
clearly says "won't fix", and surfaces everything else as a CANDIDATE together
with its note. The agent still reads each candidate's note to make the final
call (see SKILL.md). Never rely on inclusion keywords ("改", "fix") — false
positives ("故無風險", "可以改但風險不高") contain them too.

Usage:
    python3 collect_actionable.py reviewed1.xlsx [reviewed2.xlsx ...]
    python3 collect_actionable.py *.xlsx --json out.json
"""
import sys
import re
import json
import argparse
import os
import openpyxl

# Notes containing any of these phrases mean the reviewer decided NOT to fix.
# Keep this list additive; add new no-fix phrasings as they show up in review.
NO_FIX = [
    "不修改", "不用修改", "不需修補", "不做修改", "不需修改", "無需修改",
    "不處理", "不需處理", "無需處理", "暫不改", "暫時不改動", "暫時不做修改",
    "暫緩", "風險不高不", "風險低不", "無風險", "沒有任何風險", "不會有風險",
    "如 reason 描述", "如reason描述", "誤報", "屬誤報", "為誤報",
    "故無", "只是", "無法竄改",
]


def norm(v):
    return str(v).strip() if v is not None else ""


def find_header(rows):
    for i, r in enumerate(rows):
        if any("decision" in norm(c).lower() for c in r):
            return i, [norm(c) for c in r]
    return None, None


def col_index(header):
    def find(*subs):
        for sub in subs:
            for j, c in enumerate(header):
                if sub in c.lower():
                    return j
        return None
    return {
        "no": find("no.", "no", "#"),
        "level": find("risk", "level", "severity"),
        "cat": find("category"),
        "loc": find("location", "file"),
        "owasp": find("owasp"),
        "abstract": find("abstract"),
        "decision": find("decision"),
        "reason": find("reason"),
        "note": find("status", "note"),
    }


def meta_lookup(rows, key):
    for r in rows:
        if len(r) >= 2 and norm(r[0]).lower() == key.lower():
            return norm(r[1])
    return ""


def scan_tag(path, rows):
    """YYMM-ish tag: prefer the filename stem digits, else Source PDF, else ''."""
    base = os.path.basename(path)
    m = re.search(r"-(\d{4})(?:\D|$)", base)
    if m:
        return m.group(1)
    return ""


def is_no_fix(note):
    return any(p in note for p in NO_FIX)


def parse_sheet(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hi, header = find_header(rows)
    if hi is None:
        return {"file": os.path.basename(path), "error": "no header row with 'Decision' found"}
    ci = col_index(header)
    project = meta_lookup(rows[:hi], "Project") or os.path.basename(path).split("-")[0]
    tag = scan_tag(path, rows[:hi])
    findings = []
    for r in rows[hi + 1:]:
        if all(norm(c) == "" for c in r):
            continue
        get = lambda k: norm(r[ci[k]]) if ci[k] is not None and ci[k] < len(r) else ""
        note = get("note")
        if note == "" or note.startswith("=CONCATENATE"):
            # Broken Excel formula cells resolve to their fallback ("不修改");
            # with data_only they may be None. Treat empty as unreviewed.
            note_effective = note
        else:
            note_effective = note
        findings.append({
            "no": get("no").replace(".0", ""),
            "level": get("level"),
            "category": get("cat"),
            "location": get("loc"),
            "owasp": get("owasp"),
            "decision": get("decision"),
            "note": note_effective,
            "no_fix": is_no_fix(note_effective),
        })
    return {"file": os.path.basename(path), "project": project, "scan": tag, "findings": findings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", help="also write full result as JSON to this path")
    args = ap.parse_args()

    sheets = [parse_sheet(p) for p in args.files]
    errs = [s for s in sheets if s.get("error")]
    for s in errs:
        print("WARN %s: %s" % (s["file"], s["error"]), file=sys.stderr)
    sheets = [s for s in sheets if not s.get("error")]

    # group by project; keep every scan so the agent can pick the latest as canonical
    by_project = {}
    for s in sheets:
        by_project.setdefault(s["project"], []).append(s)

    print("=" * 70)
    print("ACTIONABLE CANDIDATES (reviewer did NOT mark as won't-fix)")
    print("The agent must still read each note to make the final call.")
    print("=" * 70)
    for project, scans in sorted(by_project.items()):
        scans.sort(key=lambda s: s["scan"])
        latest = scans[-1]["scan"]
        print("\n########## %s  (scans: %s | canonical=%s) ##########"
              % (project, ", ".join(s["scan"] for s in scans), latest))
        for s in scans:
            cand = [f for f in s["findings"] if not f["no_fix"]]
            nofix = [f for f in s["findings"] if f["no_fix"]]
            print("\n--- %s : %d candidates / %d findings (%d marked won't-fix) ---"
                  % (s["file"], len(cand), len(s["findings"]), len(nofix)))
            for f in cand:
                print("  #%s [%s] %s | %s" % (f["no"], f["level"], f["category"], f["location"]))
                print("     decision=%s" % f["decision"])
                print("     NOTE: %s" % f["note"].replace("\n", " "))

    if args.json:
        json.dump(by_project, open(args.json, "w"), ensure_ascii=False, indent=1)
        print("\nWrote JSON -> %s" % args.json)


if __name__ == "__main__":
    main()
