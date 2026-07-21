#!/usr/bin/env python3
"""Build the university course-name -> NxtWave tag crosswalk, ID-keyed.

Reads data/raw/subjects/NIAT 2025 - 1st Year All Subjects Data.xlsx (the
"NIAT25 Sem-N subjects status" sheets) and writes data/canonical/subjects/subject_tags.csv:
one row per (institute, course) mapping the university's LOCAL course name to the
canonical NxtWave TAG, keyed by institute_id and course_id.

Universities name the same subject differently (MRV "Quantitative Skills" =
NxtWave "Quantitative Aptitude"); this table is the authoritative normalisation.

Usage: python scripts/build_subject_tags.py
"""
import csv, os, re, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsx_dump import shared_strings, sheet_map, read_sheet

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = "data/raw/subjects/NIAT 2025 - 1st Year All Subjects Data.xlsx"
OUT = "data/canonical/subjects/subject_tags.csv"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# Sheet uses short university names; map to the institute_name used in delivery data.
# Chalapathy is split into CITY/CIET in delivery — map to the high-volume CITY campus.
ALIAS = {
    "AURORA": "Aurora University", "MRV": "Malla Reddy Vishwavidyapeeth",
    "NIAT Chevella": "NIAT Chevella", "ADYPU": "A Dy Patil University",
    "S Vyasa": "S-VYASA", "VGU": "Vivekananda global University",
    "Yenepoya": "Yenapoya University", "CDU": "Chaitanya Deemed-to-be University",
    "NSRIT": "NSRIT University", "Chalapathy": "Chalapathy (CITY)",
    "CRESCENT": "Crescent University", "Takshashila": "Takshasila University",
    "SGU": "Sanjay Ghodawat University", "Annamacharya": "Annamacharya University",
    "NRI": "NRI", "NIU": "Noida International University", "AMET": "AMET",
}


def grids(path):
    z = zipfile.ZipFile(path)
    sst = shared_strings(z)
    return [(name, read_sheet(z, p, sst)) for name, p in sheet_map(z)]


def first_uuid(s):
    m = UUID.search(s or "")
    return m.group(0) if m else ""


def main():
    rows_out, unmapped = [], set()
    for name, grid in grids(RAW):
        low = name.lower()
        if "subjects status" not in low:
            continue
        semester = "Semester 1" if "sem-1" in low else "Semester 2" if "sem-2" in low else name
        hdr = [h.strip() for h in grid[0]]
        ix = {h: i for i, h in enumerate(hdr)}
        g = lambda r, k: (r[ix[k]].strip() if ix.get(k) is not None and len(r) > ix[k] else "")
        for r in grid[1:]:
            uni = g(r, "UNVERSITY NAME") or g(r, "UNIVERSITY NAME")
            course = g(r, "COURSE NAMES")
            tag = g(r, "TAGS")
            if not (uni and course and tag):
                continue
            institute = ALIAS.get(uni)
            if institute is None:
                unmapped.add(uni)
                institute = uni  # pass through, visible
            rows_out.append({
                "semester": semester,
                "institute_id": g(r, "INSTITUTE ID"),
                "university_short": uni,
                "institute_name": institute,
                "university_course": course,
                "nxtwave_tag": tag,
                "course_id": first_uuid(g(r, "COURSE LINKS")),
                "credits": g(r, "Credits") or g(r, "CREDITS"),
            })

    cols = ["semester", "institute_id", "university_short", "institute_name",
            "university_course", "nxtwave_tag", "course_id", "credits"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows_out)

    from collections import Counter
    print(f"  subject_tags.csv: {len(rows_out)} rows")
    print(f"    universities: {len({r['institute_name'] for r in rows_out})}  "
          f"tags: {len({r['nxtwave_tag'] for r in rows_out})}  "
          f"with institute_id: {sum(1 for r in rows_out if r['institute_id'])}  "
          f"with course_id: {sum(1 for r in rows_out if r['course_id'])}")
    by_sem = Counter(r["semester"] for r in rows_out)
    print("    by semester:", dict(by_sem))
    if unmapped:
        print(f"  WARNING unmapped university short-names (passed through): {sorted(unmapped)}")
    assert rows_out, "no subject-tag rows extracted — check the sheet"
    assert not unmapped, f"unmapped universities: {unmapped} — extend ALIAS"


if __name__ == "__main__":
    main()
