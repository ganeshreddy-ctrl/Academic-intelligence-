#!/usr/bin/env python3
"""Extend the subjects sheet to cover real courses it doesn't list yet.

The base sheet (subject_tags.csv) is NxtWave's 1st-year subjects. Delivery has
many real courses beyond it — later-semester subjects (DBMS, DAA, Back End Dev)
and typo/spacing variants of 1st-year ones ("DataBase Management System",
"Web  Application Development -2", "AI For Finanace"). This maps those to
canonical tags so the crosswalk stays the source of truth.

Scope guardrails:
  - REAL universities only: we map courses for institutes already in the base
    sheet, which excludes internal DC/ops/training entities by construction.
  - Non-curriculum noise (assessments/orientation/tests) is filtered out — same
    rule as is_curriculum() in load_duckdb.py.
  - Only confident mappings are written; anything unmatched is reported, not guessed.

Output: data/canonical/subjects/subject_tags_supplement.csv, merged into subject_tags by
load_duckdb.py. Re-run after delivery data changes. Reads committed files only.

Usage: python scripts/build_subject_tags_supplement.py
"""
import csv, os, re, sys

import duckdb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "data/canonical/subjects/subject_tags.csv"
DELIV = "data/canonical/delivery/delivered_niat.parquet"
OUT = "data/canonical/subjects/subject_tags_supplement.csv"


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def tag_for(title):
    """Canonical nxtwave_tag for a delivered course_title, or None if unsure.

    Existing tags reused where the course is the same subject under a messy name;
    a few clearly-real recurring later-semester subjects get new canonical tags.
    """
    n = norm(title)
    # --- existing 1st-year tags (typo/spacing/casing variants) ---
    if "application development" in n and "web" in n:
        return "Web Application Development 2" if re.search(r"\b2\b", n) else "Web Application Development 1"
    if "web development programm" in n:                    # "Web Development Programmining"
        return "Web Application Development 1"
    if "database" in n or "dbms" in n:
        return "Database Management Systems"
    if "data structure" in n:
        return "Data Structures"
    if "numerical ability" in n:
        return "Numerical Ability"
    if "quantitaive aptitude" in n or "quantitative aptitude" in n:
        return "Quantitative Aptitude"
    if "llm" in n:
        return "Building LLM Applications"
    if "generative ai" in n or "gen ai" in n:
        return "Introduction to Generative AI"
    if any(k in n for k in ("python programming", "programming with python",
                            "problem solving using python", "problem solving with python",
                            "programming for problem solving", "problem solving",
                            "computer programming", "programming foundations")):
        return "Computer Programming"
    if any(k in n for k in ("mathematics for computer science", "math for computer science",
                            "mathematics for data science", "mathematics 1", "mathematics 2")):
        return "Mathematics for Computer Science"
    if "advanced communication skills" in n:               # distinct from English course
        return "Advanced Communication Skills"
    if ("advanced english" in n or "english advance" in n or "communicative english advanced" in n
            or "english language proficiency" in n or "applied communicative english" in n):
        return "Communicative English Advanced"
    if ("communication english foundation" in n or "communicative english foundation" in n
            or "english basic" in n):
        return "Communicative English Foundation"
    # --- new canonical tags: clearly-real recurring later-semester subjects ---
    if "design and analysis of algorithms" in n or "algorithm design" in n or n == "daa":
        return "Design and Analysis of Algorithms"
    if "back end development" in n or "backend development" in n:
        return "Back End Development"
    if "probability and statistics" in n:
        return "Probability and Statistics"
    if "ai for finance" in n or "ai for finanace" in n:
        return "AI for Finance"
    if "logical reasoning" in n:
        return "Logical Reasoning and Analytical Skills"
    return None


def main():
    con = duckdb.connect()
    con.execute(f"CREATE TABLE base AS SELECT * FROM read_csv_auto('{BASE}', header=true, all_varchar=true)")
    con.execute(f"CREATE TABLE deliv AS SELECT * FROM read_parquet('{DELIV}')")
    # HLID plan course names too, mapped to institute via the universities code table —
    # so an HLID-only name ("Programming for problem solving") resolves to its subject.
    con.execute("CREATE TABLE unis AS SELECT * FROM read_csv_auto('data/canonical/planning/standards/universities.csv', header=true, all_varchar=true)")
    con.execute("CREATE TABLE plan AS SELECT * FROM read_csv_auto('data/canonical/planning/designed/designed_course_plan.csv', header=true, all_varchar=true)")
    # noise filter — mirrors is_curriculum() in load_duckdb.py
    con.execute("""CREATE MACRO is_curriculum(t) AS (
        t IS NOT NULL AND lower(t) NOT LIKE '%assessment%' AND lower(t) NOT LIKE '%test your%'
        AND lower(t) NOT LIKE '%test based%' AND lower(t) NOT LIKE '%introduction to niat%'
        AND lower(t) NOT LIKE '%orientation%' AND lower(t) NOT LIKE '%foreign language%')""")
    # course_key — mirrors load_duckdb.py; used to skip only TRUE near-duplicates of the base.
    con.execute(r"""CREATE MACRO course_key(t) AS (regexp_replace(regexp_replace(regexp_replace(
        regexp_replace(regexp_replace(regexp_replace(regexp_replace(lower(trim(t)), '[-:_]', ' ', 'g'),
        '\s+iv$', '4'), '\s+iii$', '3'), '\s+ii$', '2'), '\s+i$', '1'), '[^a-z0-9]', '', 'g'), '1$', ''))""")

    # institute_id + university_short come from the base sheet; joining on it also
    # restricts us to REAL universities (internal DC/ops entities aren't in the sheet).
    ids = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT institute_name, any_value(institute_id), any_value(university_short) FROM base GROUP BY 1").fetchall()}
    already = {(r[0], norm(r[1])) for r in con.execute(
        "SELECT institute_name, university_course FROM base").fetchall()}
    # Skip only TRUE near-duplicates of the base: a delivered name whose course_key
    # matches a base name (e.g. "Mathematics for Data Science" == base "…- I"), which
    # the base already resolves. Delivered names that differ from the base (e.g.
    # "Web Development Programmining" vs base "Web Technologies") are KEPT — they are the
    # only thing linking that delivered course to its subject.
    base_keys = {(r[0], r[1]) for r in con.execute(
        "SELECT institute_name, course_key(university_course) FROM base").fetchall()}

    # candidate names = delivered curriculum courses + HLID plan course names
    rows = con.execute("""
        WITH cand AS (
            SELECT institute_name, semester, course_title FROM deliv WHERE is_curriculum(course_title)
            UNION
            SELECT u.institute_name, 'Semester 1', p.course
            FROM plan p JOIN unis u ON u.code = p.university
            WHERE lower(coalesce(p.is_submodule,'false')) <> 'true'
        )
        SELECT institute_name, semester, course_title, count(*) n FROM cand GROUP BY 1,2,3""").fetchall()
    ck = {r[0]: r[1] for r in con.execute(
        "SELECT DISTINCT course_title, course_key(course_title) FROM ("
        "  SELECT course_title FROM deliv WHERE is_curriculum(course_title) "
        "  UNION SELECT p.course FROM plan p WHERE lower(coalesce(p.is_submodule,'false')) <> 'true')").fetchall()}

    out, unmapped = [], []
    seen = set()
    for inst, sem, course, n in rows:
        if inst not in ids:                          # not a real (sheeted) university
            continue
        if (inst, norm(course)) in already:          # base sheet already maps it
            continue
        tag = tag_for(course)
        if not tag:
            unmapped.append((inst, sem, course, n))
            continue
        if (inst, ck.get(course)) in base_keys:         # same course_key as a base row (true dup)
            continue
        key = (sem, inst, norm(course))
        if key in seen:
            continue
        seen.add(key)
        iid, short = ids[inst]
        out.append({"semester": sem, "institute_id": iid, "university_short": short,
                    "institute_name": inst, "university_course": course,
                    "nxtwave_tag": tag, "course_id": "", "credits": ""})

    cols = ["semester", "institute_id", "university_short", "institute_name",
            "university_course", "nxtwave_tag", "course_id", "credits"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(sorted(out, key=lambda r: (r["institute_name"], r["nxtwave_tag"])))

    from collections import Counter
    print(f"  subject_tags_supplement.csv: {len(out)} rows across "
          f"{len({r['institute_name'] for r in out})} universities")
    print("    new/reused tags:", dict(Counter(r["nxtwave_tag"] for r in out)))
    print(f"\n  left unmapped (real universities, reported not guessed): {len(unmapped)} course-instances")
    seen_u = set()
    for inst, sem, course, n in sorted(unmapped, key=lambda x: -x[3]):
        if norm(course) in seen_u:
            continue
        seen_u.add(norm(course))
        print(f"    {str(course)[:44]:44s} e.g. {str(inst)[:22]:22s} {sem} ({n})")
    assert out, "no supplement rows produced — check mappings"


if __name__ == "__main__":
    main()
