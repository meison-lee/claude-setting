#!/usr/bin/env python3
"""Derive the output filename stem for a Fortify report Excel.

Style:  <short-project>-<YYMM>   e.g.  gateway-2606, auth-2606

    * short-project = the last "-" segment of the report's project name
      (gama-api-gateway -> gateway, gama-auth -> auth, gama-sender -> sender,
       gama-backpack -> backpack).
    * YYMM = the month the *commit was implemented*, taken from the commit's
      AUTHOR date — NOT the report generation time, which can drift when a
      report is regenerated/back-filled later.

Usage:
    python3 outname.py <findings.json> [--base DIR] [--month YYMM]

Resolution order for the month (author date of meta.commit):
    1. local git repo at <base>/<project>
    2. GitLab via glab (project path guessed as gama-pass/backend/<project>)
    3. give up -> exit non-zero so the caller can STOP AND ASK the user.
       (Never silently fall back to the report's scan date.)

Prints the stem (e.g. "gateway-2606") to stdout on success.
"""
import argparse
import json
import os
import re
import subprocess
import sys


def short_name(project):
    return project.strip().split("-")[-1].lower()


def repo_bases():
    bases = []
    env = os.environ.get("GAMA_REPO_BASE")
    if env:
        bases.append(env)
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if top:
            bases.append(os.path.dirname(top))
    except Exception:
        pass
    bases.append(os.path.expanduser("~/Gama"))
    # de-dup, preserve order
    seen, out = set(), []
    for b in bases:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def month_from_local_git(project, commit):
    for base in repo_bases():
        repo = os.path.join(base, project)
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        try:
            yymm = subprocess.check_output(
                ["git", "-C", repo, "show", "-s",
                 "--format=%ad", "--date=format:%y%m", commit],
                stderr=subprocess.DEVNULL, text=True,
            ).strip()
            if re.fullmatch(r"\d{4}", yymm):
                return yymm, f"local git ({repo}, author date)"
        except Exception:
            continue
    return None, None


def month_from_glab(project, commit):
    # Best-effort: the Gama backend repos live under gama-pass/backend/<project>.
    path = f"gama-pass%2Fbackend%2F{project}"
    try:
        out = subprocess.check_output(
            ["glab", "api", f"projects/{path}/repository/commits/{commit}"],
            stderr=subprocess.DEVNULL, text=True,
        )
        data = json.loads(out)
        # authored_date like "2026-06-12T09:00:00.000+08:00"
        m = re.match(r"(\d{4})-(\d{2})", data.get("authored_date", ""))
        if m:
            return m.group(1)[2:] + m.group(2), "glab (authored_date)"
    except Exception:
        pass
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--base", default=None, help="repo search base override")
    ap.add_argument("--month", default=None,
                    help="explicit YYMM to use (skips commit lookup)")
    args = ap.parse_args()

    if args.base:
        os.environ["GAMA_REPO_BASE"] = args.base

    with open(args.json) as fh:
        meta = json.load(fh).get("meta", {})
    project = meta.get("project")
    commit = meta.get("commit")
    if not project:
        print("ERROR: no project name in findings JSON.", file=sys.stderr)
        sys.exit(2)

    short = short_name(project)

    if args.month:
        if not re.fullmatch(r"\d{4}", args.month):
            print("ERROR: --month must be YYMM (e.g. 2606).", file=sys.stderr)
            sys.exit(2)
        print(f"{short}-{args.month}")
        return

    if not commit:
        print(
            "ERROR: no commit hash in the report filename, so the implementation "
            "month cannot be resolved.\n"
            "STOP AND ASK the user for the month (YYMM) or re-run with --month.",
            file=sys.stderr,
        )
        sys.exit(3)

    yymm, source = month_from_local_git(project, commit)
    if not yymm:
        yymm, source = month_from_glab(project, commit)
    if not yymm:
        print(
            f"ERROR: could not resolve the author-date month for commit "
            f"{commit} of {project} (not found in local repos or via glab).\n"
            "STOP AND ASK the user — do NOT fall back to the report's scan date.\n"
            "Re-run with --month YYMM once you know it.",
            file=sys.stderr,
        )
        sys.exit(3)

    print(f"{short}-{yymm}")
    print(f"(month {yymm} from {source})", file=sys.stderr)


if __name__ == "__main__":
    main()
