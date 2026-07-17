#!/usr/bin/env python3
"""Build the upload checklist from the Central Catalogue's Stack sheet.

Reads data/raw/catalogue/stack.csv (authoritative), cross-checks against what
we've actually ingested, writes data/courses.csv, prints a grouped checklist.
"""
import csv, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# course_id -> ingested source dir (verified loads)
INGESTED = {
    "4b8803cc-8ecb-4284-9fcf-53c5afd2a93c": "data/raw/python-course/",
    "e216af3e-bcd0-4dee-9c4f-67e7502ecba3": "data/raw/dsa-cpp/",
    "40ab5ebd-3def-4faf-adca-3d39d921df1c": "data/raw/react-course/",
    "d82d6905-6694-42c4-8c0c-bd2c887c1b53": "data/raw/backend-node-course/",
}

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
