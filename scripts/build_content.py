#!/usr/bin/env python3
"""Flatten course content exports (xlsx + json) into one committed, queryable table.

Handles the several export shapes seen in the wild:
  - Full xlsx: Course Outline + Objective/Classroom-Quiz/Coding-Practice JSON sheets
    (options embedded as JSON in cells).
  - Reading-only xlsx: readings inline in a sheet (named "Course Outline" or "Sheet1")
    with a "Reading Material Content" column; questions live elsewhere.
  - Standalone .json: a list of content units (questions + learning resources) with
    answer / difficulty / explanation — the payload the xlsx's "JSONs" sheet links to.

Writes data/canonical/content/ingested/course_content.csv, one row per content unit, JSON parsed to
plain text. Drop any of the above into data/raw/content/ and re-run.

Usage: python scripts/build_content.py
"""
import ast, csv, glob, json, os, re, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsx_dump import shared_strings, sheet_map, read_sheet

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = "data/raw/content"
OUT = "data/canonical/content/ingested/course_content.csv"
COLS = ["course", "module", "topic", "session_id", "session_name", "unit_id", "unit_name",
        "kind", "question_type", "difficulty", "content", "options", "correct_answer",
        "explanation", "code"]


def strip_html(s):
    return re.sub(r"<[^>]+>", " ", s or "").replace("&nbsp;", " ").strip()


def parse_json_list(raw):
    """Available_options / JSON-array answer -> ' | '-joined content strings."""
    try:
        arr = json.loads(raw) if raw and raw.strip().startswith("[") else []
        return " | ".join(o.get("content", "").strip() for o in arr if isinstance(o, dict))
    except (json.JSONDecodeError, TypeError):
        return ""


def parse_answer(raw):
    if not raw:
        return ""
    return parse_json_list(raw) if raw.strip().startswith("[") else raw.strip()


def parse_explanation(raw):
    """answer_explanation is a stringified python dict {'content':..,'content_type':..}."""
    if not raw or not str(raw).strip():
        return ""
    try:
        d = ast.literal_eval(raw) if isinstance(raw, str) else raw
        return strip_html(d.get("content", "")) if isinstance(d, dict) else strip_html(str(raw))
    except (ValueError, SyntaxError):
        return strip_html(str(raw))


def rec(**kw):
    base = {c: "" for c in COLS}
    base.update(kw)
    return base


# ---------- xlsx ----------
def sheets(path):
    z = zipfile.ZipFile(path)
    sst = shared_strings(z)
    out = {}
    for name, p in sheet_map(z):
        grid = read_sheet(z, p, sst)
        if grid and grid[0]:
            hdr = [h.strip() for h in grid[0]]
            out[name] = [dict(zip(hdr, r)) for r in grid[1:] if any(c.strip() for c in r)]
    return out


def ci(row, *names):
    """case-insensitive column fetch, tolerant of trailing spaces."""
    low = {k.lower().strip(): v for k, v in row.items()}
    for n in names:
        v = low.get(n.lower().strip())
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def extract_xlsx(path):
    sh = sheets(path)
    course = ""
    for rows in sh.values():
        for r in rows:
            course = ci(r, "Course Name", "Course name", "Course Title")
            if course:
                break
        if course:
            break
    if not course:
        course = re.sub(r"\s*(Course\s*)?Contents?$", "", os.path.splitext(os.path.basename(path))[0], flags=re.I).strip()
    grp = lambda r: ci(r, "Module Name", "Topic Name")
    out = []

    # readings — join any "Reading Material Content..." column(s) on a row into one
    # reading. Handles both the single-column shape and the Content-repository shape
    # where content is paged across "Reading Material Content 1 (Page 1)", "(Page 2)"...
    for rows in sh.values():
        for r in rows:
            pages = [str(v).strip() for k, v in r.items()
                     if k.lower().strip().startswith("reading material content") and str(v).strip()]
            if not pages:
                continue
            out.append(rec(course=course, module=grp(r), topic=ci(r, "Topic Name", "Session Name"),
                           session_id=ci(r, "Session ID"), session_name=ci(r, "Session Name"),
                           unit_id=ci(r, "Unit ID", "Reading Material id", "Reading Material Name"),
                           kind="reading", content="\n\n".join(pages)))

    # questions — from the embedded JSON sheets when present
    for sheet, kind in [("Objective Content JSON", "objective"), ("Classroom Quiz JSON", "classroom_quiz")]:
        for r in sh.get(sheet, []):
            if not ci(r, "Content"):
                continue
            out.append(rec(course=course, module=grp(r), topic=ci(r, "Topic Name"),
                           session_id=ci(r, "Session ID"), session_name=ci(r, "Session Name"),
                           unit_id=ci(r, "Unit ID"), unit_name=ci(r, "Unit Name"), kind=kind,
                           question_type=ci(r, "Question_type"), content=strip_html(ci(r, "Content")),
                           options=parse_json_list(ci(r, "Available_options")),
                           correct_answer=parse_answer(ci(r, "Correct_answer")), code=ci(r, "Code")))
    for r in sh.get("Coding Practice JSON", []):
        if not ci(r, "Content"):
            continue
        out.append(rec(course=course, module=grp(r), topic=ci(r, "Topic Name"),
                       session_id=ci(r, "Session ID"), session_name=ci(r, "Session Name"),
                       unit_id=ci(r, "Unit ID"), unit_name=ci(r, "Unit Name"), kind="coding",
                       content=strip_html(ci(r, "Content")), code=ci(r, "code_id")))
    return course, out


# ---------- json ----------
def _obj_kind(obj):
    obj = (obj or "").upper()
    return "reading" if obj == "LEARNING_RESOURCE" else "coding" if obj == "CODING_QUESTIONS" else "objective"


def extract_json(path):
    data = json.load(open(path, encoding="utf-8"))
    default = os.path.splitext(os.path.basename(path))[0]
    out = []

    # Shape A: nested course -> topics -> units -> questions (e.g. GenAI coding questions)
    if isinstance(data, dict) and "topics" in data:
        course = data.get("course_title") or default
        for t in data.get("topics", []):
            topic = t.get("topic_title") or ""
            for u in t.get("units", []):
                uid, uname = u.get("unit_id") or "", u.get("unit_title") or ""
                for q in u.get("questions", []):
                    content = strip_html(q.get("question_text") or q.get("content") or "") or (q.get("short_text") or "").strip()
                    if not content:
                        continue
                    out.append(rec(course=course, topic=topic, unit_id=uid, unit_name=uname, kind="coding",
                                   question_type=q.get("question_type") or "",
                                   difficulty=(q.get("difficulty_label") or q.get("toughness") or "").strip(),
                                   content=content, code=str(q.get("default_code") or "")))
        return course, out

    # Shape B: flat list of content units (QA / building-llm / intro-swd exports)
    if isinstance(data, list):
        course = next((x.get("course_title") for x in data if x.get("course_title")), default)
        for x in data:
            content = strip_html(x.get("content") or "") or (x.get("short_text") or "").strip()
            if not content:
                continue
            out.append(rec(course=x.get("course_title") or course, topic=x.get("topic_name") or "",
                           unit_id=x.get("unit_id") or "", unit_name=x.get("unit_name") or "",
                           kind=_obj_kind(x.get("object_type")),
                           question_type=x.get("question_type") or "", difficulty=(x.get("difficulty") or "").strip(),
                           content=content, correct_answer=strip_html(str(x.get("answer") or "")),
                           explanation=parse_explanation(x.get("answer_explanation"))))
        return course, out
    return "", []


def main():
    files = sorted(glob.glob(os.path.join(RAW, "*.xlsx")) + glob.glob(os.path.join(RAW, "*.json")))
    assert files, f"no content exports in {RAW}/"
    all_recs = []
    from collections import Counter
    for f in files:
        course, recs = extract_json(f) if f.endswith(".json") else extract_xlsx(f)
        all_recs += recs
        print(f"  {os.path.basename(f)}: {course} -> {len(recs)} units  {dict(Counter(r['kind'] for r in recs))}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_recs)
    print(f"  course_content.csv: {len(all_recs)} rows, {len({r['course'] for r in all_recs})} courses")
    assert all_recs, "no content extracted"
    mcq = [r for r in all_recs if r["options"]]
    assert not any(r["options"].strip().startswith("[{") for r in mcq), "options JSON not parsed"


if __name__ == "__main__":
    main()
