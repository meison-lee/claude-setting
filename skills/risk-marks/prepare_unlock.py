#!/usr/bin/env python3
"""Turn a 客服/申訴 unlock list (gamapassID) into the phone list to DELETE, plus a
report of what the phone delete will NOT cover.

The unlock list only ever gives openIDs, but the marks that actually exist on PROD
are phone-type rows. This script does the mapping and — more importantly — tells you
which targets the phone delete cannot reach:

  * targets with no phone in any batch mapping   -> phone delete is a no-op for them
  * targets that are in the 第一批 openID list    -> they also carry an openID-type mark,
                                                    which a phone delete does NOT remove

Usage:
    python3 prepare_unlock.py --targets "/path/....csv" --tag 2026-09-04

Writes <out-dir>/unlock_phones_<tag>.csv (one +E164 per line, deduplicated, no header)
which is the --file argument for delete_risk_marks.py --type phone.

Standard library only.
"""

import argparse
import csv
import os
import re
import sys
import zipfile

DATA_DIR = os.path.expanduser("~/Gama/tools/script/api-risk-marks/data")

# Batch mappings: openID -> phone. Add a row here when a new 黑名單批次 lands.
MAPPINGS = [
    ("第一批 GAMAPASS-3531", os.path.join(DATA_DIR, "GAMAPASS-3531_openid_phone_mapping.csv")),
    ("第二批 GAMAPASS-3589", os.path.join(DATA_DIR, "GAMAPASS-3589_openid_phone_mapping.xlsx")),
]
# openID-type marks that were imported directly (not derived from a phone).
OPENID_MARK_LISTS = [
    ("第一批 GAMAPASS-3531", os.path.join(DATA_DIR, "GAMAPASS-3531_risk_openIDs.csv")),
]

OPENID_WORDS = ("openid", "open_id", "gamapassid", "gamapass_id")
PHONE_WORDS = ("phone", "手機", "電話", "mobile")
COUNTRY_WORDS = ("國碼", "country")


def read_xlsx(path):
    """Yield rows (list of str) from every sheet, no dependencies."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S):
            shared.append("".join(re.findall(r"<t[^>]*>([^<]*)</t>", si)))
    for name in sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet")):
        for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read(name).decode(), re.S):
            cells = {}
            for col, attr, inner in re.findall(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', row, re.S):
                v = re.search(r"<v>([^<]*)</v>", inner or "")
                v = v.group(1) if v else ""
                if 't="s"' in attr and v != "":
                    v = shared[int(v)]
                elif 't="inlineStr"' in attr:
                    v = "".join(re.findall(r"<t[^>]*>([^<]*)</t>", inner or ""))
                cells[col] = v.strip()
            if any(cells.values()):
                width = max(_col_index(c) for c in cells) + 1
                out = [""] * width
                for c, v in cells.items():
                    out[_col_index(c)] = v
                yield out


def _col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_rows(path):
    if path.lower().endswith(".xlsx"):
        yield from read_xlsx(path)
        return
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if any(c.strip() for c in row):
                yield [c.strip() for c in row]


def find_col(header, words, default):
    for i, h in enumerate(header):
        if any(w in h.lower() for w in words):
            return i
    return default


def looks_like_header(row):
    """A row is a header when its first cell is not a bare openID.

    The unlock lists ship headers the scripts do not know ('gamapassID(解鎖)'),
    so detect by shape, not by a word list: real openIDs are digits only.
    """
    first = row[0] if row else ""
    return not first.isdigit()


def normalise_phone(value):
    value = re.sub(r"[\s\-()]", "", value)
    if value.endswith(".0"):
        value = value[:-2]
    if value.startswith("+"):
        return value if value[1:].isdigit() else None
    return "+" + value if value.isdigit() else None


def read_targets(path):
    """Deduplicated openIDs from the unlock list's openID column, file order kept."""
    targets, seen, col = [], set(), 0
    for row in read_rows(path):
        if looks_like_header(row):
            col = find_col(row, OPENID_WORDS, 0)
            continue
        oid = row[col] if len(row) > col else ""
        if oid and oid not in seen:
            seen.add(oid)
            targets.append(oid)
    return targets


def read_mapping(path):
    """openID -> set of whole phones. Handles a split 國碼/號碼 pair or one whole column."""
    mapping, id_col, ph_col, cc_col = {}, 0, 1, None
    for row in read_rows(path):
        if looks_like_header(row):
            id_col = find_col(row, OPENID_WORDS, 0)
            ph_col = find_col(row, PHONE_WORDS, 1)
            cc = find_col(row, COUNTRY_WORDS, -1)
            cc_col = cc if cc >= 0 and cc != ph_col else None
            continue
        need = max(id_col, ph_col, cc_col if cc_col is not None else 0)
        if len(row) <= need:
            continue
        oid = row[id_col]
        raw = (row[cc_col] + row[ph_col]) if cc_col is not None else row[ph_col]
        phone = normalise_phone(raw)
        if oid and phone:
            mapping.setdefault(oid, set()).add(phone)
    return mapping


def read_id_list(path):
    return {row[0] for row in read_rows(path) if row and row[0].isdigit()}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--targets", required=True, help="the 解鎖 list (csv or xlsx)")
    p.add_argument("--tag", required=True, help="date tag for the output file, e.g. 2026-09-04")
    p.add_argument("--out-dir", default=DATA_DIR)
    args = p.parse_args()

    targets = read_targets(args.targets)
    print(f"targets: {len(targets)} unique openIDs")

    phones_by_target, per_mapping = {}, []
    for label, path in MAPPINGS:
        if not os.path.exists(path):
            print(f"WARNING: mapping missing, skipped: {path}", file=sys.stderr)
            continue
        mapping = read_mapping(path)
        hit = 0
        for oid in targets:
            found = mapping.get(oid)
            if found:
                hit += 1
                phones_by_target.setdefault(oid, {})[label] = sorted(found)
        per_mapping.append((label, hit, len(mapping)))
        print(f"  {label}: {hit}/{len(targets)} matched (mapping has {len(mapping)} openIDs)")

    union = sorted({ph for byb in phones_by_target.values() for phs in byb.values() for ph in phs})
    out_path = os.path.join(args.out_dir, f"unlock_phones_{args.tag}.csv")
    with open(out_path, "w", encoding="utf-8") as f:
        for ph in union:
            f.write(ph + "\n")
    print(f"\nphone list -> {out_path}  ({len(union)} unique phones, union of all batches)")

    # The 解鎖 list's own header ('gamapassID(解鎖)') is not in the delete script's
    # HEADER_WORDS, so never point --type openID at the raw 客服 file. Emit a clean one.
    oid_path = os.path.join(args.out_dir, f"unlock_openids_{args.tag}.csv")
    with open(oid_path, "w", encoding="utf-8") as f:
        for oid in targets:
            f.write(oid + "\n")
    print(f"openID list -> {oid_path}  ({len(targets)} openIDs, header stripped — "
          f"use this for --type openID, never the raw 客服 CSV)")

    # Which batch does each phone come from? A phone that only exists in a batch whose
    # phone marks were already bulk-deleted will come back not-found — expected, not an error.
    labels_by_phone = {}
    for byb in phones_by_target.values():
        for label, phs in byb.items():
            for ph in phs:
                labels_by_phone.setdefault(ph, set()).add(label)
    for label, _, _ in per_mapping:
        only = sorted(ph for ph, labels in labels_by_phone.items() if labels == {label})
        if only:
            print(f"   {len(only)} phone(s) come ONLY from {label}: {', '.join(only)}")

    no_phone = [oid for oid in targets if oid not in phones_by_target]
    if no_phone:
        print(f"\n!! {len(no_phone)} target(s) have NO phone in any mapping — "
              f"the phone delete does nothing for them:")
        for oid in no_phone:
            print(f"     {oid}")

    multi = {oid: byb for oid, byb in phones_by_target.items()
             if len({ph for phs in byb.values() for ph in phs}) > 1}
    if multi:
        print(f"\n   {len(multi)} target(s) have different phones across batches "
              f"(all of them are in the list above, that is why it is a union):")
        for oid, byb in multi.items():
            detail = "; ".join(f"{label}={','.join(phs)}" for label, phs in byb.items())
            print(f"     {oid}: {detail}")

    for label, path in OPENID_MARK_LISTS:
        if not os.path.exists(path):
            print(f"WARNING: openID mark list missing, skipped: {path}", file=sys.stderr)
            continue
        also = [oid for oid in targets if oid in read_id_list(path)]
        if also:
            print(f"\n!! {len(also)}/{len(targets)} target(s) are in the {label} openID mark list. "
                  f"A phone delete does NOT remove an openID-type mark.")
            print(f"   Confirm on PROD, then ask the user whether to delete these too:")
            ids = ", ".join(f"'{o}'" for o in also)
            print(f"     SELECT id, risk_type_id, open_id, operation_reason, created_time")
            print(f"     FROM user_risk_marks WHERE open_id IN ({ids});")


if __name__ == "__main__":
    main()
