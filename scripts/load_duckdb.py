#!/usr/bin/env python3
"""Assemble data/aip.duckdb from the git-committed canonical files + courses.csv.

No raw data needed — this is what makes the repo self-sufficient: a fresh clone
(or a Streamlit Cloud deploy, which only ever sees git) can rebuild the queryable
store from what's committed.

Views exist to pre-solve joins a caller would otherwise get wrong. That is the
whole point of them: `deviation` in particular encodes the trickiest join in the
store so nobody re-derives it per question.

Usage: python scripts/load_duckdb.py
"""
import duckdb, glob, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def build(db="data/aip.duckdb", verbose=True):
    if os.path.exists(db):
        os.remove(db)
    con = duckdb.connect(db)

    sources = [("courses", "data/courses.csv")]
    for p in (sorted(glob.glob("data/canonical/**/*.csv", recursive=True))
              + sorted(glob.glob("data/canonical/**/*.parquet", recursive=True))):
        sources.append((os.path.splitext(os.path.basename(p))[0], p))
    for name, path in sources:
        p = path.replace(os.sep, "/")
        reader = (f"read_parquet('{p}')" if p.endswith(".parquet")
                  else f"read_csv_auto('{p}', header=true, all_varchar=true)")
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM {reader}")

    # Merge the sheet extension into subject_tags (same columns), then drop the
    # extra table so the crosswalk stays one table. See build_subject_tags_supplement.py.
    if ("subject_tags_supplement",) in con.execute("SHOW TABLES").fetchall():
        con.execute("INSERT INTO subject_tags SELECT * FROM subject_tags_supplement")
        con.execute("DROP TABLE subject_tags_supplement")
    # drop any fully-identical rows (a few slipped into the base sheet)
    con.execute("CREATE TABLE _st AS SELECT DISTINCT * FROM subject_tags")
    con.execute("DROP TABLE subject_tags")
    con.execute("ALTER TABLE _st RENAME TO subject_tags")

    # --- views ---

    # is_curriculum: the subjects sheet is the source of truth for what a real
    # subject/course is. Delivery data mixes in non-curriculum noise — orientation,
    # placement tests, and assessment blocks — which are not subjects and must not
    # show up as courses. This is the one place that noise is defined; reused by the
    # views here and by the Explorer. Real courses the sheet hasn't mapped yet are a
    # crosswalk-coverage gap, NOT noise — they pass this filter and are kept.
    # ponytail: pattern list, small and stable; move to a committed CSV only if it grows.
    con.execute("""CREATE MACRO is_curriculum(t) AS (
        t IS NOT NULL
        AND lower(t) NOT LIKE '%assessment%'
        AND lower(t) NOT LIKE '%test your%'
        AND lower(t) NOT LIKE '%test based%'
        AND lower(t) NOT LIKE '%introduction to niat%'
        AND lower(t) NOT LIKE '%orientation%'
        AND lower(t) NOT LIKE '%foreign language%')""")

    # Variant-tolerant course keys so the same course under cosmetically-different
    # names matches without duplicate rows. course_key_loose collapses case, separators,
    # spacing and roman->arabic ("Web App Dev II" = "…-2"), keeping the number so 1 != 2;
    # use it with a prefix match (tolerates appended words like "…(Workshop)").
    # course_key additionally drops a trailing 1 so "Web App Dev" == "Web App Dev 1" under
    # an EXACT match (the Alignment tab). Don't prefix-match course_key — the strip would
    # make "…dev" a prefix of "…dev2" and wrongly merge 1 and 2.
    con.execute(r"""CREATE MACRO course_key_loose(t) AS (
        regexp_replace(
          regexp_replace(
            regexp_replace(
              regexp_replace(
                regexp_replace(
                  regexp_replace(lower(trim(t)), '[-:_]', ' ', 'g'),
                '\s+iv$', '4'),
              '\s+iii$', '3'),
            '\s+ii$', '2'),
          '\s+i$', '1'),
        '[^a-z0-9]', '', 'g'))""")
    con.execute("CREATE MACRO course_key(t) AS (regexp_replace(course_key_loose(t), '1$', ''))")

    # content_units: unified view over the three content-item tables.
    con.execute("""CREATE VIEW content_units AS
        SELECT unit_id, course_title, 'objective' AS k FROM objective_questions
        UNION ALL SELECT unit_id, course_title, 'coding'  FROM coding_questions
        UNION ALL SELECT unit_id, course_title, 'reading' FROM reading_materials""")

    # session_feedback_safe: ratings + counts, WITHOUT the student comment text.
    # The agent is pointed here, never at the base table — the app deploys from a
    # repo to third-party infra and free-text student complaints must not leave.
    con.execute("""CREATE VIEW session_feedback_safe AS
        SELECT institute_name, session_id, session_title, unit_ids,
               total_feedbacks, session_understanding_rating, teaching_quality_rating
        FROM session_feedback""")

    # delivered_sections: delivered_sessions.batch_section_name is a COMMA-SEPARATED
    # LIST ("TU Batch-1-S-002, TU Batch-1-S-003"), so one row covers several sections.
    # Counting it raw counts section-groupings, not sections. This explodes it.
    con.execute("""CREATE VIEW delivered_sections AS
        SELECT d.institute_name, d.semester, d.session_id, d.unit_id,
               d.session_type, d.start_ts, trim(s.section) AS section
        FROM delivered_sessions d,
             unnest(string_split(d.batch_section_name, ',')) AS s(section)
        WHERE trim(s.section) <> ''""")

    # deviation: designed vs delivered, per university, on unit_id — the hardest join
    # in the store, encoded once. Semester 1 only: designed data covers Sem 1 only.
    con.execute("""CREATE VIEW deviation AS
        WITH d AS (
            SELECT ds.university,
                   u.institute_name,
                   ds.unit_id,
                   any_value(ds.course)        AS course,
                   min(ds.planned_start)       AS planned_start
            FROM designed_sequence ds
            JOIN universities u ON u.code = ds.university
            WHERE ds.unit_id IS NOT NULL AND ds.unit_id <> ''
            GROUP BY 1, 2, 3
        ),
        v AS (
            -- ONLY institutes that have designed data on file. Without this, delivered
            -- units at the other 14 institutes get labelled 'added' when the truth is
            -- simply that no design exists to compare against.
            SELECT institute_name, unit_id, min(start_ts) AS actual_start
            FROM delivered_sessions
            WHERE semester = 'Semester 1'
              AND institute_name IN (SELECT institute_name FROM universities)
            GROUP BY 1, 2
        )
        SELECT
            coalesce(d.university, u2.code)            AS university,
            coalesce(d.institute_name, v.institute_name) AS institute_name,
            d.course,
            coalesce(d.unit_id, v.unit_id)             AS unit_id,
            try_cast(d.planned_start AS DATE)          AS planned_start,
            v.actual_start,
            date_diff('day', try_cast(d.planned_start AS DATE), v.actual_start) AS drift_days,
            CASE WHEN d.unit_id IS NOT NULL AND v.unit_id IS NOT NULL THEN 'delivered'
                 WHEN d.unit_id IS NOT NULL THEN 'dropped'
                 ELSE 'added' END                      AS status
        FROM d
        FULL OUTER JOIN v
          ON d.unit_id = v.unit_id AND d.institute_name = v.institute_name
        LEFT JOIN universities u2 ON u2.institute_name = v.institute_name""")

    # course_plan_vs_actual: the whole planned-vs-delivered comparison, per course,
    # already normalised PER SECTION. This is the single most-asked analytical shape
    # ("how did the plan hold up", "give me a better HLID") and it takes ~7 dependent
    # queries to assemble by hand — more than an agent reliably finishes. Encoded once.
    #
    # FULL OUTER on purpose: courses planned-but-never-delivered AND delivered-but-never
    # -planned (MRV ran Introduction to NIAT, Test Your Current Knowledge and Foreign
    # Language, none of which are in its HLID) are both real findings.
    con.execute("""CREATE VIEW course_plan_vs_actual AS
        WITH plan AS (
            SELECT p.university, u.institute_name, p.course,
                   course_key_loose(p.course) AS k,
                   TRY_CAST(p.sessions_count AS DOUBLE)         AS planned_sessions,
                   TRY_CAST(p.session_hours AS DOUBLE)          AS planned_session_hours,
                   TRY_CAST(p.practice_hours AS DOUBLE)         AS planned_practice_hours,
                   TRY_CAST(p.micro_assessment_hours AS DOUBLE) AS planned_micro_hours,
                   coalesce(TRY_CAST(p.session_hours AS DOUBLE),0)
                     + coalesce(TRY_CAST(p.practice_hours AS DOUBLE),0)
                     + coalesce(TRY_CAST(p.micro_assessment_hours AS DOUBLE),0) AS planned_total_hours,
                   try_cast(p.start_timeline AS DATE)           AS planned_start,
                   try_cast(p.end_timeline AS DATE)             AS planned_end,
                   TRY_CAST(p.weeks_required AS DOUBLE)         AS planned_weeks
            FROM designed_course_plan p
            JOIN universities u ON u.code = p.university
            -- sub-modules are components of the course above them; including them double-counts
            WHERE lower(coalesce(p.is_submodule,'false')) <> 'true'
        ),
        secs AS (
            SELECT institute_name, count(DISTINCT section_name) AS n_sections
            FROM delivered_niat WHERE semester = 'Semester 1' GROUP BY 1
        ),
        act AS (
            SELECT d.institute_name, d.course_title,
                   course_key_loose(d.course_title) AS k,
                   s.n_sections,
                   round(count(*) FILTER (WHERE d.session_type='LECTURE')  * 1.0 / s.n_sections, 1) AS actual_lectures_per_section,
                   round(count(*) FILTER (WHERE d.session_type='PRACTICE') * 1.0 / s.n_sections, 1) AS actual_practice_per_section,
                   round(count(*) FILTER (WHERE d.session_type='EXAM')     * 1.0 / s.n_sections, 1) AS actual_exam_per_section,
                   min(d.start_ts)::DATE AS actual_start,
                   max(d.start_ts)::DATE AS actual_end,
                   count(DISTINCT date_trunc('week', d.start_ts)) AS actual_weeks,
                   round(100.0 * count(*) FILTER (WHERE d.session_status='COMPLETED') / count(*), 0) AS pct_completed
            FROM delivered_niat d
            JOIN secs s ON s.institute_name = d.institute_name
            WHERE d.semester = 'Semester 1' AND d.is_scheduled
            GROUP BY 1, 2, 3, 4
        )
        SELECT
            coalesce(plan.university, u2.code)                 AS university,
            coalesce(plan.institute_name, act.institute_name)  AS institute_name,
            coalesce(plan.course, act.course_title)            AS course,
            CASE WHEN plan.k IS NULL THEN 'delivered_not_planned'
                 WHEN act.k  IS NULL THEN 'planned_not_delivered'
                 ELSE 'both' END                               AS coverage,
            plan.planned_sessions, plan.planned_session_hours, plan.planned_practice_hours,
            plan.planned_micro_hours, plan.planned_total_hours,
            plan.planned_start, plan.planned_end, plan.planned_weeks,
            act.actual_lectures_per_section, act.actual_practice_per_section,
            act.actual_exam_per_section, act.actual_start, act.actual_end,
            act.actual_weeks, act.pct_completed, act.n_sections,
            date_diff('day', plan.planned_start, act.actual_start) AS start_slip_days,
            act.actual_lectures_per_section - plan.planned_sessions AS session_gap
        FROM plan
        FULL OUTER JOIN act
          ON plan.institute_name = act.institute_name
         AND (plan.k = act.k OR starts_with(plan.k, act.k) OR starts_with(act.k, plan.k))
        LEFT JOIN universities u2 ON u2.institute_name = act.institute_name
        WHERE coalesce(plan.university, u2.code) IS NOT NULL""")

    # content_all: ONE inventory across both content systems. Content lives in two
    # places — the older catalogue tables (reading_materials/objective_questions/
    # coding_questions, ~15 courses) and the newer course_content (ingested exports).
    # An eval showed the agent checked only one and wrongly reported content "missing".
    # This view is the single answer to "what content exists / which courses / how much".
    con.execute("""CREATE VIEW content_all AS
        SELECT course_title AS course, 'reading'   AS kind, unit_id, 'catalogue' AS source FROM reading_materials
        UNION ALL SELECT course_title, 'objective', unit_id, 'catalogue' FROM objective_questions
        UNION ALL SELECT course_title, 'coding',    unit_id, 'catalogue' FROM coding_questions
        UNION ALL SELECT course, kind, unit_id, 'ingested' FROM course_content""")

    # college_summary: one row per college — the at-a-glance health view. Powers the
    # copilot's most common questions ("how is X doing", "compare colleges", "which is
    # struggling") so it doesn't reassemble the same 4-table join every time.
    # Semester 1. Only is_scheduled sessions count toward completion.
    con.execute("""CREATE VIEW college_summary AS
        WITH d AS (
            SELECT institute_name,
                   count(DISTINCT section_name)                          AS sections,
                   count(DISTINCT course_title)                          AS courses,
                   count(*) FILTER (WHERE is_scheduled)                  AS scheduled_sessions,
                   round(100.0 * count(*) FILTER (WHERE session_status='COMPLETED')
                         / nullif(count(*) FILTER (WHERE is_scheduled), 0), 0) AS pct_completed,
                   min(start_ts) FILTER (WHERE is_scheduled)::DATE       AS first_session,
                   max(start_ts) FILTER (WHERE is_scheduled)::DATE       AS last_session,
                   count(DISTINCT date_trunc('week', start_ts)
                         ) FILTER (WHERE is_scheduled)                   AS teaching_weeks
            FROM delivered_niat WHERE semester='Semester 1' GROUP BY 1
        ),
        f AS (
            SELECT institute_name,
                   round(avg(TRY_CAST(session_understanding_rating AS DOUBLE)), 2) AS avg_understanding,
                   round(avg(TRY_CAST(teaching_quality_rating AS DOUBLE)), 2)      AS avg_teaching,
                   count(*)                                              AS rated_sessions
            FROM session_feedback_safe GROUP BY 1
        ),
        i AS (SELECT institute_name, count(DISTINCT issue_id) AS recorded_issues FROM issues GROUP BY 1)
        SELECT d.institute_name, d.sections, d.courses, d.scheduled_sessions, d.pct_completed,
               d.teaching_weeks, d.first_session, d.last_session,
               f.avg_understanding, f.avg_teaching, coalesce(f.rated_sessions, 0) AS rated_sessions,
               coalesce(i.recorded_issues, 0) AS recorded_issues,
               (u.code IS NOT NULL) AS has_designed_plan
        FROM d
        LEFT JOIN f USING (institute_name)
        LEFT JOIN i USING (institute_name)
        LEFT JOIN universities u ON u.institute_name = d.institute_name
        -- real colleges only: drop internal distribution/training/ops entries
        WHERE d.scheduled_sessions > 100
          AND d.institute_name NOT ILIKE '%DC'
          AND d.institute_name NOT IN ('Training Institute', 'Program_Ops')""")

    # session_link: the fuzzy bridge reconnecting the two delivery tables that share no
    # key. delivered_niat (course + instructor + status) has no session_id/unit_id;
    # delivered_sessions (session_id + unit_id + feedback link) has no course/instructor.
    # Bridge on institute + session_title + start-minute (~76% match). `linked` flags it,
    # so the break stays visible rather than silently dropping rows.
    con.execute("""CREATE VIEW session_link AS
        WITH smin AS (
            SELECT institute_name, lower(trim(session_title)) AS tkey,
                   date_trunc('minute', start_ts) AS tmin,
                   any_value(session_id) AS session_id, any_value(unit_id) AS unit_id,
                   any_value(resource_type) AS resource_type
            FROM delivered_sessions WHERE session_title IS NOT NULL GROUP BY 1, 2, 3),
        sday AS (
            SELECT institute_name, lower(trim(session_title)) AS tkey, start_ts::DATE AS tday,
                   any_value(session_id) AS session_id, any_value(unit_id) AS unit_id,
                   any_value(resource_type) AS resource_type
            FROM delivered_sessions WHERE session_title IS NOT NULL GROUP BY 1, 2, 3)
        SELECT n.institute_name, n.semester, n.course_title, n.session_title, n.session_type,
               n.instructor_name, n.instructor_category, n.session_status, n.section_name,
               n.start_ts, n.end_ts, n.is_scheduled,
               coalesce(sm.session_id, sd.session_id)     AS session_id,
               coalesce(sm.unit_id, sd.unit_id)           AS unit_id,
               coalesce(sm.resource_type, sd.resource_type) AS resource_type,
               (coalesce(sm.session_id, sd.session_id) IS NOT NULL) AS linked,
               -- 'minute' = same time (high confidence); 'day' = same title+day fallback
               CASE WHEN sm.session_id IS NOT NULL THEN 'minute'
                    WHEN sd.session_id IS NOT NULL THEN 'day' ELSE 'none' END AS link_precision
        FROM delivered_niat n
        LEFT JOIN smin sm ON sm.institute_name = n.institute_name
                         AND sm.tkey = lower(trim(n.session_title))
                         AND sm.tmin = date_trunc('minute', n.start_ts)
        LEFT JOIN sday sd ON sd.institute_name = n.institute_name
                         AND sd.tkey = lower(trim(n.session_title))
                         AND sd.tday = n.start_ts::DATE""")

    # academic_plan_derived: planning-style metrics from DELIVERY, per
    # (institute, semester, course), for ALL universities — designed plans exist for
    # only 4, so this is the universal "plan" layer (label it derived, not designed).
    con.execute("""CREATE VIEW academic_plan_derived AS
        WITH secs AS (SELECT institute_name, semester, count(DISTINCT section_name) n_sections
                      FROM delivered_niat GROUP BY 1, 2),
             cohort AS (SELECT institute_name, semester, min(start_ts)::DATE cohort_start
                        FROM delivered_niat WHERE is_scheduled GROUP BY 1, 2)
        SELECT d.institute_name, d.semester, d.course_title,
               -- lecture (teaching) sessions per section — the same basis as the HLID's
               -- planned session count (planned ≈ lectures), so this matches the Designed
               -- plan's Actual/section for the same course instead of contradicting it.
               round(count(*) FILTER (WHERE d.is_scheduled AND d.session_type='LECTURE') * 1.0
                     / nullif(sc.n_sections, 0), 1) AS sessions_per_section,
               count(*) FILTER (WHERE d.is_scheduled)                             AS scheduled_sessions,
               count(DISTINCT date_trunc('week', d.start_ts)) FILTER (WHERE d.is_scheduled) AS teaching_weeks,
               min(d.start_ts) FILTER (WHERE d.is_scheduled)::DATE                AS first_session,
               max(d.start_ts) FILTER (WHERE d.is_scheduled)::DATE                AS last_session,
               date_diff('day', any_value(co.cohort_start),
                         min(d.start_ts) FILTER (WHERE d.is_scheduled)::DATE)     AS start_slip_days,
               round(100.0 * count(*) FILTER (WHERE d.session_status='COMPLETED')
                     / nullif(count(*) FILTER (WHERE d.is_scheduled), 0), 0)      AS pct_completed
        FROM delivered_niat d
        JOIN secs sc   USING (institute_name, semester)
        JOIN cohort co USING (institute_name, semester)
        WHERE is_curriculum(d.course_title)
        GROUP BY d.institute_name, d.semester, d.course_title, sc.n_sections""")

    if verbose:
        print("=== aip.duckdb (from committed canonical) ===")
        for (t,) in con.execute("SHOW TABLES").fetchall():
            n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n} rows")

    tables = [t for (t,) in con.execute("SHOW TABLES").fetchall()]
    assert "courses" in tables and len(tables) > 1, "no canonical tables loaded"
    con.close()
    return db


if __name__ == "__main__":
    build()
