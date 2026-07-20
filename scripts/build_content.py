#!/usr/bin/env python3
"""Flatten course content exports into one committed, queryable table.

Reads every *.xlsx in data/raw/content/ (each a course's content export with the
sheets: Course Outline, Objective/Classroom-Quiz/Coding-Practice JSON) and writes
data/canonical/course_content.csv — one row per content unit, with the embedded
JSON (options, answers) parsed to plain text.

Drop a new course's content xlsx into data/raw/content/ and re-run — this is the
content-coverage pipeline (content previously reached only ~15 of 63 courses).

Usage: python scripts/build_content.py
"""
import csv, glob, json, os, re, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsx_dump import shared_strings, sheet_map, read_sheet

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = "data/raw/content"
OUT = "data/canonical/course_content.csv"


def strip_html(s):
    return re.sub(r"<[^>]+>", " ", s or "").replace("&nbsp;", " ").strip()


def parse_options(raw):
    try:
        arr = json.loads(raw) if raw and raw.strip().startswith("[") else []
        return " | ".join(o.get("content", "").strip() for o in arr if isinstance(o, dict))
    except (json.JSONDecodeError, TypeError):
        return ""


def parse_answer(raw):
    if not raw:
        return ""
    if raw.strip().startswith("["):
        try:
            return " | ".join(o.get("content", "").strip() for o in json.loads(raw) if isinstance(o, dict))
        except (json.JSONDecodeError, TypeError):
            return raw.strip()
    return raw.strip()


def sheets(path):
    z = zipfile.ZipFile(path)
    sst = shared_strings(z)
    out = {}
    for name, p in sheet_map(z):
        grid = read_sheet(z, p, sst)
        if grid:
            hdr = grid[0]
            out[name] = (hdr, [dict(zip(hdr, r)) for r in grid[1:] if any(c.strip() for c in r)])
    return out


def extract(path):
    sh = sheets(path)
    recs = []

    def course_of(rowset):
        for r in rowset:
            if r.get("Course Name"):
                return r["Course Name"]
        return os.path.splitext(os.path.basename(path))[0]

    outline = sh.get("Course Outline", (None, []))[1]
    course = course_of(outline)

    # reading materials (markdown/text in the outline)
    for r in outline:
        content = (r.get("Reading Material Content") or "").strip()
        if content:
            recs.append(dict(course=course, module=r.get("Module Name", ""), topic="",
                             session_id=r.get("Session ID", ""), session_name=r.get("Session Name", ""),
                             unit_id=r.get("Reading Material id", ""), unit_name="", kind="reading",
                             question_type="", content=content, options="", correct_answer="", code=""))

    # objective + classroom-quiz questions (parse the JSON option arrays)
    for sheet, kind in [("Objective Content JSON", "objective"),
                        ("Classroom Quiz JSON", "classroom_quiz")]:
        for r in sh.get(sheet, (None, []))[1]:
            if not (r.get("Content") or "").strip():
                continue
            recs.append(dict(course=course, module=r.get("Module Name", ""), topic="",
                             session_id=r.get("Session ID", ""), session_name=r.get("Session Name", ""),
                             unit_id=r.get("Unit ID", ""), unit_name=r.get("Unit Name", ""), kind=kind,
                             question_type=r.get("Question_type", ""), content=strip_html(r.get("Content", "")),
                             options=parse_options(r.get("Available_options", "")),
                             correct_answer=parse_answer(r.get("Correct_answer", "")),
                             code=(r.get("Code", "") or "").strip()))

    # coding practice
    for r in sh.get("Coding Practice JSON", (None, []))[1]:
        if not (r.get("Content") or "").strip():
            continue
        recs.append(dict(course=course, module=r.get("Module Name", ""), topic="",
                         session_id=r.get("Session ID", ""), session_name=r.get("Session Name", ""),
                         unit_id=r.get("Unit ID", ""), unit_name=r.get("Unit Name", ""), kind="coding",
                         question_type="", content=strip_html(r.get("Content", "")), options="",
                         correct_answer="", code=r.get("code_id", "")))
    return course, recs


def main():
    files = sorted(glob.glob(os.path.join(RAW, "*.xlsx")))
    assert files, f"no content exports in {RAW}/ — drop a course content xlsx there"
    cols = ["course", "module", "topic", "session_id", "session_name", "unit_id",
            "unit_name", "kind", "question_type", "content", "options", "correct_answer", "code"]
    all_recs = []
    for f in files:
        course, recs = extract(f)
        all_recs += recs
        from collections import Counter
        kinds = Counter(r["kind"] for r in recs)
        print(f"  {os.path.basename(f)}: {course} -> {len(recs)} units  {dict(kinds)}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_recs)
    print(f"  course_content.csv: {len(all_recs)} rows, {len({r['course'] for r in all_recs})} course(s)")
    assert all_recs, "no content extracted"
    # options must actually be parsed (not left as raw JSON) for MCQ-type questions
    mcq = [r for r in all_recs if r["kind"] in ("objective", "classroom_quiz") and r["options"]]
    assert not any(r["options"].strip().startswith("[{") for r in mcq), "options JSON not parsed"


if __name__ == "__main__":
    main()
