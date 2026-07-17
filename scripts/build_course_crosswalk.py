#!/usr/bin/env python3
"""Build data/canonical/course_crosswalk.csv — bridges course titles across layers
(delivered scheduling, content, catalogue) via a normalized course_key.

Auto-matches to the catalogue by normalized key (exact, then containment). Titles
that don't match are flagged 'unmapped' for manual aliasing — we do NOT guess a
catalogue course for them.  ponytail: normalized-key match is the 80%; the long
tail of genuinely uncatalogued names is a human decision, surfaced not fabricated.

Usage: python scripts/build_course_crosswalk.py
"""
import csv, os, re, glob
import duckdb

RAW_NIAT = "data/raw/scheduling/niat-scheduled-session-details.csv"
CANON = "data/canonical"
OUT = f"{CANON}/course_crosswalk.csv"
con = duckdb.connect()

def ckey(s):
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\badvance\b", "advanced", s)   # merge advance/advanced spelling variants
    s = re.sub(r"\s+", " ", s)
    return s

def distinct(sql):
    return [r[0].strip() for r in con.execute(sql).fetchall() if r[0] and r[0].strip()]

# --- source titles per layer ---
catalogue = con.execute(
    "SELECT DISTINCT course_title, stack, course_ids FROM "
    "read_csv_auto('data/courses.csv', header=true, all_varchar=true) WHERE course_title IS NOT NULL"
).fetchall()
cat_by_key = {}
for title, stack, cids in catalogue:
    cat_by_key.setdefault(ckey(title), (title, stack or "", cids or ""))

delivered = distinct(f"SELECT DISTINCT \"Course Title\" FROM read_csv_auto('{RAW_NIAT}', header=true, all_varchar=true, ignore_errors=true)")
content = []
for p in glob.glob(f"{CANON}/*.csv"):
    cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_csv_auto('{p.replace(os.sep,'/')}', header=true, all_varchar=true)").fetchall()]
    if "course_title" in cols:
        content += distinct(f"SELECT DISTINCT course_title FROM read_csv_auto('{p.replace(os.sep,'/')}', header=true, all_varchar=true)")

def match(key):
    """return (status, catalogue_title, stack) — exact, partial(containment), or unmapped."""
    if key in cat_by_key:
        t, s, _ = cat_by_key[key]; return "exact", t, s
    # containment: key is a substring of a catalogue key or vice-versa (guard against trivial short keys)
    if len(key) >= 6:
        for ck, (t, s, _) in cat_by_key.items():
            if len(ck) >= 6 and (key in ck or ck in key):
                return "partial", t, s
    return "unmapped", "", ""

rows = []
seen = set()
for layer, titles in [("catalogue", [c[0] for c in catalogue]), ("delivered", delivered), ("content", content)]:
    for t in titles:
        key = ckey(t)
        dedup = (layer, key)
        if dedup in seen:
            continue
        seen.add(dedup)
        if layer == "catalogue":
            status, ctitle, stack = "self", t, (cat_by_key.get(key, ("", "", ""))[1])
        else:
            status, ctitle, stack = match(key)
        rows.append((layer, t, key, status, ctitle, stack))

os.makedirs(CANON, exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["layer", "raw_title", "course_key", "match_status", "catalogue_course_title", "stack"])
    w.writerows(rows)

# summary
from collections import Counter
print(f"  course_crosswalk.csv: {len(rows)} rows -> {OUT}")
for layer in ("delivered", "content"):
    c = Counter(r[3] for r in rows if r[0] == layer)
    tot = sum(c.values())
    print(f"    {layer:9s}: {tot:3d} titles  |  " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
