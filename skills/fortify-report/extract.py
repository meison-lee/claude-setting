#!/usr/bin/env python3
"""Extract report metadata and findings from a Fortify Developer Workbook PDF.

Usage:
    python3 extract.py <report.pdf> [-o findings.json]

Emits JSON with two keys:
    "meta"     -> report attributes (project, commit, scan date, SCA version, LOC, counts)
    "findings" -> list of one record per Fortify issue

The finding anchor in the "Issues Description" section is reliable:

    <location>, line <N> (<Category>)
    Fortify Priority: <Level> Folder <Level>

Each such anchor occurrence is one issue (the same sink can legitimately appear
more than once with different source traces, and Fortify counts those
separately) so we do NOT deduplicate by location. Instead we cross-check the
parsed count against the report's own severity totals and warn on any mismatch.
"""
import argparse
import json
import os
import re
import sys

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - fallback for older installs
    from PyPDF2 import PdfReader


def strip_footers(text):
    """Remove the recurring page footer so it never bleeds into a finding.

    The footer is three lines: the workbook-name token, the copyright line, and
    the wrapped total-page count, e.g.:

        CloudForce_DeveloperWorkbook_en
        Copyright 2025 gamania CloudForce Company Limited. Page 4 of
        29

    The line above the copyright line is always the workbook-name token, so we
    drop it too without hardcoding the report name.
    """
    return re.sub(
        r"[^\n]*\n[^\n]*Copyright \d{4}[^\n]*Page \d+ of\s*\n?\s*\d+",
        "",
        text,
    )


def load_text(pdf_path):
    reader = PdfReader(pdf_path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return strip_footers(text)


def commit_from_filename(pdf_path):
    """Fortify PDFs are often named <project>-<40-char-sha>[ suffix].pdf."""
    base = os.path.basename(pdf_path)
    m = re.search(r"([0-9a-f]{40}|[0-9a-f]{7,12})", base)
    return m.group(1) if m else None


def parse_meta(text, pdf_path):
    meta = {
        "source_pdf": os.path.basename(pdf_path),
        "commit": commit_from_filename(pdf_path),
        "project": None,
        "scan_date": None,
        "machine": None,
        "sca_version": None,
        "filter_set": None,
        "files_scanned": None,
        "loc": None,
        "total_issues": None,
        "counts": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0},
    }

    m = re.search(
        r"On (.+?), a source code review was performed over the (.+?) code base"
        r"(?: on machine (.+?)\.)?",
        text,
        re.S,
    )
    if m:
        meta["scan_date"] = clean_ws(m.group(1))
        # strip a trailing "(BuildID)" style note from the project name
        meta["project"] = re.sub(r"\s*\(.*?\)\s*$", "", clean_ws(m.group(2)))
        if m.group(3):
            # hostnames wrap on a trailing hyphen: "devops-\nfortify-sca-01"
            meta["machine"] = clean_ws(m.group(3).replace("-\n", "-"))

    m = re.search(r"SCA Engine version ([\d.]+)", text)
    if m:
        meta["sca_version"] = m.group(1)

    m = re.search(r"Enabled Filter Set being (.+?)\.", text)
    if m:
        meta["filter_set"] = m.group(1).strip()

    m = re.search(
        r"([\d,]+)\s+files,\s+([\d,]+)\s+LOC.*?A total of\s+(\d+)\s+issues",
        text,
        re.S,
    )
    if m:
        meta["files_scanned"] = int(m.group(1).replace(",", ""))
        meta["loc"] = int(m.group(2).replace(",", ""))
        meta["total_issues"] = int(m.group(3))

    # Report Summary block: "Critical 6\nHigh 3\nMedium 0\nLow 0"
    for level in ("Critical", "High", "Medium", "Low"):
        m = re.search(rf"^{level}\s+(\d+)\s*$", text, re.M)
        if m:
            meta["counts"][level] = int(m.group(1))

    return meta


ANCHOR = re.compile(
    # A long location can make Fortify wrap the anchor line, splitting the
    # "(Category)" parenthetical across a newline, so the category group must
    # allow newlines (clean_ws collapses them later). It still stops at the
    # first ")", and categories never contain one.
    r"^(?P<loc>[^\n,]+?), line (?P<line>\d+) \((?P<category>[^)]+?)\)\s*\n"
    r"\s*Fortify Priority:\s*(?P<level>\w+)",
    re.M,
)


def field(block, pattern, flags=0):
    m = re.search(pattern, block, flags)
    return m.group(1).strip() if m else None


def clean_ws(s):
    return re.sub(r"\s+", " ", s).strip() if s else s


def parse_findings(text):
    matches = list(ANCHOR.finditer(text))
    findings = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        kingdom = field(block, r"Kingdom:\s*(.+?)\s*OWASP Top", re.S)
        owasp = field(
            block,
            r"OWASP Top\s*10\s*20\d\d\s*(A\d+.+?)"
            r"(?=\n(?:Abstract|Source|Sink|Instance ID)\b|\Z)",
            re.S,
        )
        abstract = field(
            block,
            r"Abstract:\s*(.+?)(?:\nSource:|\nSink:|\nInstance ID|\Z)",
            re.S,
        )
        source = field(block, r"Source:\s*([^\n]+)")
        sink = field(block, r"Sink:\s*([^\n]+)")

        findings.append(
            {
                "no": i + 1,
                "level": m.group("level"),
                "category": clean_ws(m.group("category")),
                "location": f"{m.group('loc').strip()}:{m.group('line')}",
                "owasp": clean_ws(owasp),
                "kingdom": clean_ws(kingdom),
                "abstract": clean_ws(abstract),
                "source": clean_ws(source),
                "sink": clean_ws(sink),
            }
        )
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    text = load_text(args.pdf)
    meta = parse_meta(text, args.pdf)
    findings = parse_findings(text)

    # Cross-check parsed count against the report's own totals.
    expected = meta.get("total_issues")
    warnings = []
    if expected is not None and expected != len(findings):
        warnings.append(
            f"Parsed {len(findings)} findings but report states {expected}. "
            "Review the PDF layout — the parser may be missing or splitting issues."
        )
    by_level = {}
    for f in findings:
        by_level[f["level"]] = by_level.get(f["level"], 0) + 1
    for level, n in meta["counts"].items():
        if n and by_level.get(level, 0) != n:
            warnings.append(
                f"{level}: report summary says {n}, parsed {by_level.get(level, 0)}."
            )

    result = {"meta": meta, "findings": findings, "warnings": warnings}
    out = args.out or (os.path.splitext(args.pdf)[0] + ".findings.json")
    with open(out, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    print(f"Wrote {out}")
    print(f"Parsed {len(findings)} findings (report total: {expected}).")
    if warnings:
        print("WARNINGS:", file=sys.stderr)
        for w in warnings:
            print("  - " + w, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
