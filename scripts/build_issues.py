#!/usr/bin/env python3
"""Flatten the recorded issues / RCA board into a committed canonical table.

Reads data/raw/issues/batch3-issues-rca.xlsx (the "Issues by RCA Group" sheet) and
writes data/canonical/issues/issues.csv — one row per (issue, university), so the agent can
join issues to a college the same way it joins everything else.

These are the RECORDED issues (the other half of the design's "derive issues AND read
a recorded log"). They capture things delivery data cannot show — platform outages,
infra limits, content defects — tagged to the 16-layer taxonomy with a solutioning
direction. The agent combines them with issues it derives from delivery.

Usage: python scripts/build_issues.py
"""
import csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsx_dump import shared_strings, sheet_map, read_sheet
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAW = "data/raw/issues/batch3-issues-rca.xlsx"
OUT = "data/canonical/issues/issues.csv"
SHEET = "Issues by RCA Group"

# Issue files use short university CODES; map them to the institute_name used everywhere
# else so issues join to delivery/feedback/plans. Codes not listed pass through as-is
# (and get flagged), so a new code is visible rather than silently dropped.
CODE_TO_INSTITUTE = {
    "aurora": "Aurora University",
    "mrv": "Malla Reddy Vishwavidyapeeth",
    "cdu": "Chaitanya Deemed-to-be University",
    "yenepoya": "Yenapoya University",
    "sgu": "Sanjay Ghodawat University",
    "svyasa": "S-VYASA",
    "s-vyasa": "S-VYASA",
}


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def primary_layer(s):
    """The layer field embeds sub-layers on new lines; take the first line as the layer."""
    first = (s or "").split("\n")[0]
    return clean(first)


def main():
    z = zipfile.ZipFile(RAW)
    sst = shared_strings(z)
    grid = next((read_sheet(z, p, sst) for name, p in sheet_map(z) if name == SHEET), None)
    assert grid, f"sheet {SHEET!r} not found in {RAW}"
    hdr = grid[0]
    ix = {h: i for i, h in enumerate(hdr)}

    def cell(row, name):
        i = ix.get(name)
        return clean(row[i]) if (i is not None and len(row) > i) else ""

    rows_out, unknown = [], set()
    for row in grid[1:]:
        iid = cell(row, "Issue ID")
        title = cell(row, "Derived Issue Title") or cell(row, "Raw Issue Title")
        if not iid or not title:
            continue
        unis_raw = cell(row, "Universities")
        codes = [c.strip() for c in unis_raw.split(",") if c.strip()] or ["(unspecified)"]
        for code in codes:
            inst = CODE_TO_INSTITUTE.get(code.lower())
            if inst is None and code != "(unspecified)":
                unknown.add(code)
                inst = code  # pass through, visible
            rows_out.append({
                "issue_id": iid,
                "university_code": code,
                "institute_name": inst or "",
                "universities_raw": unis_raw,
                "primary_layer": primary_layer(row[ix["RCA - Primary Layer"]] if "RCA - Primary Layer" in ix and len(row) > ix["RCA - Primary Layer"] else ""),
                "category": cell(row, "Category"),
                "rca_group_category": cell(row, "RCA Group Category"),
                "issue_title": title,
                "rca_description": cell(row, "RCA Description"),
                "solutioning_direction": cell(row, "Solutioning Direction"),
                "status": cell(row, "Lead Review Status"),
            })

    cols = ["issue_id", "university_code", "institute_name", "universities_raw",
            "primary_layer", "category", "rca_group_category", "issue_title",
            "rca_description", "solutioning_direction", "status"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows_out)

    n_issues = len({r["issue_id"] for r in rows_out})
    print(f"  issues.csv: {len(rows_out)} rows ({n_issues} distinct issues)")
    from collections import Counter
    for inst, c in Counter(r["institute_name"] for r in rows_out).most_common():
        print(f"    {inst or '(unspecified)':38s} {c}")
    if unknown:
        print(f"  WARNING: unmapped university codes (passed through): {sorted(unknown)}")
    assert n_issues > 50, "expected 100+ issues; parse may have changed"


if __name__ == "__main__":
    main()
