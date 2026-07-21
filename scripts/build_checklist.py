#!/usr/bin/env python3
"""Build the upload checklist from the Central Catalogue's Stack sheet.

Reads data/raw/catalogue/stack.csv (authoritative), cross-checks against what
we've actually ingested, writes data/courses.csv, prints a grouped checklist.
"""
import csv, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# loaded = any course_id present in the canonical content (source of truth),
# so this stays correct as new courses are flattened in. ponytail: derive, don't maintain a list.
import glob, os
INGESTED = {}
for cf in glob.glob("data/canonical/**/*.csv", recursive=True):
    with open(cf, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        if "course_id" not in (rd.fieldnames or []):
            continue
        for row in rd:
            if row.get("course_id"):
                INGESTED.setdefault(row["course_id"], "data/canonical/")

with open("data/raw/catalogue/stack.csv", encoding="utf-8") as f:
    rows = list(csv.reader(f))
idx = {n: i for i, n in enumerate(rows[0])}
c = lambda r, k: (r[idx[k]] if idx.get(k) is not None and idx[k] < len(r) else "").strip()

cur = ""
out = []
for r in rows[1:]:
    if c(r, "Stack"):
        cur = c(r, "Stack")
    title = c(r, "NxtWave Internal Course Title")
    if not title:
        continue
    ids = [x.strip() for x in c(r, "Course Id").replace("\n", ";").split(";") if x.strip()]
    src = next((INGESTED[i] for i in ids if i in INGESTED), "")
    has_content = bool(c(r, "Course Contents"))
    status = "loaded" if src else ("not-ingested" if has_content else "no-content")
    out.append({
        "stack": cur, "course_title": title,
        "course_outcome": c(r, "Course Outcome"),
        "course_ids": "; ".join(ids),
        "prereq_course_ids": c(r, "Prerequisite Course Ids").replace("\n", "; "),
        "content_in_catalogue": "yes" if has_content else "no",
        "has_taxonomy": "yes" if c(r, "Session Mastery Taxonomy") else "no",
        "ingest_status": status, "source_dir": src,
    })

cols = ["stack", "course_title", "course_outcome", "course_ids", "prereq_course_ids",
        "content_in_catalogue", "has_taxonomy", "ingest_status", "source_dir"]
with open("data/courses.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader(); w.writerows(out)

# ---- print checklist ----
MARK = {"loaded": "[x] LOADED     ", "not-ingested": "[ ] content ready, NOT ingested",
        "no-content": "[ ] no content yet"}
tally = {"loaded": 0, "not-ingested": 0, "no-content": 0}
stack = None
for x in out:
    if x["stack"] != stack:
        stack = x["stack"]; print(f"\n=== {stack} ===")
    tally[x["ingest_status"]] += 1
    print(f"  {MARK[x['ingest_status']]:33s} {x['course_title']}")
print("\n" + "=" * 50)
print(f"TOTAL {len(out)} courses | LOADED {tally['loaded']} | "
      f"content-ready-not-ingested {tally['not-ingested']} | no-content {tally['no-content']}")
