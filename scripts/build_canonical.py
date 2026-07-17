#!/usr/bin/env python3
"""Flatten all loaded content (JSON + Python xlsx) into canonical tables.

Outputs data/canonical/{reading_materials,objective_questions,coding_questions,
editorials}.csv and loads them (+ courses.csv) into data/aip.duckdb.

ponytail: canonical rows keep the queryable fields + IDs; bulky detail
(test-case bodies, full option sets) stays in the raw files, referenced by id.
"""
import json, csv, os, sys, glob
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(50_000_000)
import duckdb

RAW = "data/raw"
OUT = "data/canonical"
os.makedirs(OUT, exist_ok=True)

# course_id -> (title, stack) from the catalogue
CMAP = {}
with open("data/courses.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        for cid in [x.strip() for x in row["course_ids"].split(";") if x.strip()]:
            CMAP[cid] = (row["course_title"], row["stack"])
def meta(cid, embedded_title=""):
    t, s = CMAP.get(cid, ("", ""))
    return (embedded_title or t, s)

reading, objective, coding, editorial = [], [], [], []

def add_reading(cid, title, topic, unit_id, unit_title, lrid, rtype, cfmt, content, video, src):
    ct, st = meta(cid, title)
    reading.append(dict(course_id=cid, course_title=ct, stack=st, topic_name=topic,
        unit_id=unit_id, unit_title=unit_title, learning_resource_id=lrid,
        resource_type=rtype, content_format=cfmt, content=content, video_url=video, source=src))
def add_obj(cid, title, topic, unit_id, qid, qtype, diff, content, options, correct, src):
    ct, st = meta(cid, title)
    objective.append(dict(course_id=cid, course_title=ct, stack=st, topic_name=topic,
        unit_id=unit_id, question_id=qid, question_type=qtype, difficulty=diff,
        content=content, options_json=options, correct_answer=correct, source=src))
def add_cod(cid, title, topic, unit_id, qid, diff, qtitle, content, ntc, companies, src):
    ct, st = meta(cid, title)
    coding.append(dict(course_id=cid, course_title=ct, stack=st, topic_name=topic,
        unit_id=unit_id, question_id=qid, difficulty=diff, title=qtitle, content=content,
        num_test_cases=ntc, companies=companies, source=src))

def first_video(mm):
    if isinstance(mm, list) and mm and isinstance(mm[0], dict):
        return mm[0].get("multimedia_url", "")
    return ""

# ---- Extractor A: per-course-id JSON (React, Backend x3) ----
PC = {  # filename id -> course_id fallback (same here)
    "40ab5ebd-3def-4faf-adca-3d39d921df1c": "40ab5ebd-3def-4faf-adca-3d39d921df1c",
    "d82d6905-6694-42c4-8c0c-bd2c887c1b53": "d82d6905-6694-42c4-8c0c-bd2c887c1b53",
    "128b8668-816b-44eb-9f04-86a571b0b495": "128b8668-816b-44eb-9f04-86a571b0b495",
    "b785ce15-460c-4e34-b3f3-b4b1b78ed789": "b785ce15-460c-4e34-b3f3-b4b1b78ed789",
}
for fid, fallback in PC.items():
    src = fid[:8]
    with open(f"{RAW}/json/{fid}.json", encoding="utf-8") as f:
        data = json.load(f)
    for it in data:
        if "content_data" in it:  # video/reading wrapper (no course_id embedded)
            cd = it["content_data"]
            for lr in cd.get("learning_resource_details") or []:
                add_reading(fallback, "", "", it.get("unit_id"), cd.get("title"),
                    lr.get("learning_resource_id"), lr.get("learning_resource_type"),
                    lr.get("content_format"), lr.get("content", ""),
                    first_video(lr.get("multimedia_details")), src)
            continue
        cid = it.get("course_id") or fallback
        title = it.get("course_title", "")
        ot = it.get("object_type")
        if ot == "OBJECTIVE_QUESTIONS":
            add_obj(cid, title, it.get("topic_name"), it.get("unit_id"), it.get("question_id"),
                it.get("question_type"), it.get("difficulty"), it.get("content"),
                json.dumps(it.get("options"), ensure_ascii=False), "", src)
        elif ot == "CODING_QUESTIONS":
            add_cod(cid, title, it.get("topic_name"), it.get("unit_id"), it.get("question_id"),
                it.get("difficulty"), it.get("short_text"), it.get("content"),
                len(it.get("test_cases") or []), "", src)
        elif ot == "LEARNING_RESOURCE":
            add_reading(cid, title, it.get("topic_name"), it.get("unit_id"), it.get("unit_title"),
                it.get("learning_resource_id"), "LEARNING_RESOURCE", it.get("content_type"),
                it.get("content", ""), "", src)

# ---- Extractor B: DSA trio (course_id = e216af3e) ----
DSA = "e216af3e-bcd0-4dee-9c4f-67e7502ecba3"
with open(f"{RAW}/json/dsa-mcqs-reading.json", encoding="utf-8") as f:
    for u in json.load(f):
        cd = u.get("content_data", {})
        for lr in cd.get("learning_resource_details") or []:
            add_reading(DSA, "", cd.get("title"), u.get("unit_id"), cd.get("title"),
                lr.get("learning_resource_id"), lr.get("learning_resource_type"),
                lr.get("content_format"), lr.get("content", ""),
                first_video(lr.get("multimedia_details")), "dsa-mcqs-reading")
with open(f"{RAW}/json/dsa-coding-testcases.json", encoding="utf-8") as f:
    for it in json.load(f):
        q = it.get("question", {})
        comp = "; ".join(c.get("company_name", "") for c in it.get("question_asked_by_companies_info") or [])
        topic = "; ".join(q.get("topic_tag_names") or [])
        add_cod(DSA, "", topic, "", q.get("question_id"), q.get("difficulty"),
            q.get("short_text"), q.get("content"), len(it.get("test_cases") or []),
            comp, "dsa-coding-testcases")
with open(f"{RAW}/json/dsa-editorials.json", encoding="utf-8") as f:
    for it in json.load(f):
        ct, st = meta(DSA)
        editorial.append(dict(course_id=DSA, question_id=it.get("question_id"),
            content=it.get("editorial_content"), source="dsa-editorials"))

# ---- Extractor C: Python xlsx CSVs (course_id = 4b8803cc) ----
PY = "4b8803cc-8ecb-4284-9fcf-53c5afd2a93c"
def rows_of(path):
    with open(path, encoding="utf-8") as f:
        r = list(csv.reader(f))
    idx = {n: i for i, n in enumerate(r[0])}
    g = lambda row, k: row[idx[k]] if idx.get(k) is not None and idx[k] < len(row) else ""
    return [(row, g) for row in r[1:] if any(c.strip() for c in row)], g
d = f"{RAW}/python-course"
outline, g = rows_of(f"{d}/course-outline.csv")
for row, g in outline:
    if not g(row, "Session Name").strip():
        continue
    add_reading(PY, "", g(row, "Module Name"), g(row, "Session ID"), g(row, "Session Name"),
        g(row, "Reading Material id"), "READING", "MARKDOWN",
        g(row, "Reading Material Content"), g(row, "Session PPT"), "python-course-outline")
for fn, qsrc in [("objective-content-json.csv", "python-objective"),
                 ("classroom-quiz-json.csv", "python-classroom-quiz")]:
    rows, g = rows_of(f"{d}/{fn}")
    for row, g in rows:
        if not g(row, "Question_id").strip():
            continue
        add_obj(PY, "", g(row, "Session Name"), g(row, "Unit ID"), g(row, "Question_id"),
            g(row, "Question_type"), "", g(row, "Content"), g(row, "Available_options"),
            g(row, "Correct_answer"), qsrc)
rows, g = rows_of(f"{d}/coding-practice-json.csv")
for row, g in rows:
    if not g(row, "Session Name").strip():
        continue
    add_cod(PY, "", g(row, "Session Name"), g(row, "Unit ID"), g(row, "Question_id"),
        "", g(row, "Session Name"), g(row, "Content"), 0, "", "python-coding")

# ---- write canonical CSVs ----
def write(name, recs):
    if not recs:
        print(f"  {name}: 0 rows (skipped)"); return
    cols = list(recs[0].keys())
    with open(f"{OUT}/{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(recs)
    print(f"  {name}: {len(recs)} rows -> {OUT}/{name}.csv")

print("=== canonical CSVs ===")
write("reading_materials", reading)
write("objective_questions", objective)
write("coding_questions", coding)
write("editorials", editorial)

# ---- load into aip.duckdb ----
DB = "data/aip.duckdb"
if os.path.exists(DB):
    os.remove(DB)
con = duckdb.connect(DB)
con.execute(f"CREATE TABLE courses AS SELECT * FROM read_csv_auto('data/courses.csv', header=true, all_varchar=true)")
for t in ["reading_materials", "objective_questions", "coding_questions", "editorials"]:
    p = f"{OUT}/{t}.csv"
    if os.path.exists(p):
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{p}', header=true, all_varchar=true)")
print("\n=== aip.duckdb tables ===")
for (t,) in con.execute("SHOW TABLES").fetchall():
    n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n} rows")

print("\n=== content by course (proof of unified query) ===")
q = """
SELECT c.course_title,
  (SELECT count(*) FROM reading_materials r WHERE r.course_id=x.cid) AS reading,
  (SELECT count(*) FROM objective_questions o WHERE o.course_id=x.cid) AS objective,
  (SELECT count(*) FROM coding_questions g WHERE g.course_id=x.cid) AS coding
FROM (SELECT DISTINCT course_id cid FROM (
        SELECT course_id FROM reading_materials UNION ALL
        SELECT course_id FROM objective_questions UNION ALL
        SELECT course_id FROM coding_questions)) x
JOIN courses c ON list_contains(str_split(replace(c.course_ids,' ',''),';'), x.cid)
ORDER BY 1
"""
for r in con.execute(q).fetchall():
    print(f"  {r[0][:45]:45s} reading={r[1]:5d} objective={r[2]:5d} coding={r[3]:4d}")

# ponytail self-check: every canonical table non-empty and joinable
assert len(reading) and len(objective) and len(coding) and len(editorial), "a canonical table is empty"
assert con.execute("SELECT count(*) FROM coding_questions g JOIN courses c "
                   "ON list_contains(str_split(replace(c.course_ids,' ',''),';'), g.course_id)").fetchone()[0] > 0
print("\nSELF-CHECK PASSED")
con.close()
