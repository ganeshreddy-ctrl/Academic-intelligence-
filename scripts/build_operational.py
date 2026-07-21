#!/usr/bin/env python3
"""Flatten scheduling + feedback (data/raw/delivery/) into compact canonical
operational tables that link to content via unit_id.

Writes data/canonical/delivery/sessions.csv, data/canonical/feedback/session_feedback.csv,
and data/canonical/instructors/instructor_sessions.csv.
ponytail: only the small, RCA-relevant distillate is committed — the 396K raw
session INSTANCE rows stay in raw/ (bulky telemetry, regenerable).

Usage: python scripts/build_operational.py
"""
import duckdb, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

S = "data/raw/delivery"
# three outputs, three domains
OUT_SESSIONS = "data/canonical/delivery"
OUT_FEEDBACK = "data/canonical/feedback"
OUT_INSTRUCTORS = "data/canonical/instructors"
for d in (OUT_SESSIONS, OUT_FEEDBACK, OUT_INSTRUCTORS):
    os.makedirs(d, exist_ok=True)
con = duckdb.connect()
rd = lambda f: f"read_csv_auto('{S}/{f}', header=true, all_varchar=true, ignore_errors=true)"

# 1) sessions: distinct session -> unit catalogue (the link to canonical content.unit_id)
con.execute(f"""COPY (
  SELECT DISTINCT session_id, session_title, session_type, unit_id, resource_type
  FROM {rd('scheduled-session-details.csv')}
  WHERE trim(coalesce(session_id,'')) <> ''
) TO '{OUT_SESSIONS}/sessions.csv' (HEADER, DELIMITER ',')""")

# 2) session_feedback: quantitative ratings + qualitative comment text, per (institute, session, unit)
con.execute(f"""COPY (
  SELECT
    coalesce(q.institute_name, l.institute_name)  AS institute_name,
    -- normalize session_id to dash-less form so it joins sessions/scheduling (which store 32-hex, no dashes)
    lower(replace(coalesce(q.session_id, l.session_id), '-', '')) AS session_id,
    coalesce(q.session_title,  l.session_title)   AS session_title,
    coalesce(q.unit_ids,       l.unit_ids)        AS unit_ids,
    q.total_feedbacks, q.session_understanding_rating, q.teaching_quality_rating,
    l.positive_feedbacks, l.neutral_feedbacks, l.negative_feedbacks
  FROM {rd('quantitative-feedback-details.csv')} q
  FULL OUTER JOIN {rd('qualitative-feedback-details.csv')} l
    ON  q.institute_name = l.institute_name
    AND q.session_id     = l.session_id
    AND coalesce(q.unit_ids,'') = coalesce(l.unit_ids,'')
) TO '{OUT_FEEDBACK}/session_feedback.csv' (HEADER, DELIMITER ',')""")

# 3) instructor_sessions: per-instructor delivery aggregates (from NIAT)
con.execute(f"""COPY (
  SELECT "Instructor Name" AS instructor_name, "Instructor Category" AS instructor_category,
    count(*) AS total_sessions,
    count(*) FILTER (WHERE "Session Status"='COMPLETED') AS completed,
    count(*) FILTER (WHERE "Session Status"='PENDING')   AS pending,
    round(count(*) FILTER (WHERE "Session Status"='COMPLETED') * 1.0 / nullif(count(*),0), 3) AS completion_rate,
    count(DISTINCT "Institute Name") AS institutes,
    count(DISTINCT "Course Title")   AS courses
  FROM {rd('niat-scheduled-session-details.csv')}
  WHERE trim(coalesce("Instructor Name",'')) <> '' AND "Instructor Name" <> '-'
  GROUP BY 1,2 ORDER BY total_sessions DESC
) TO '{OUT_INSTRUCTORS}/instructor_sessions.csv' (HEADER, DELIMITER ',')""")

for t in ["sessions", "session_feedback", "instructor_sessions"]:
    n = con.execute(f"SELECT count(*) FROM read_csv_auto('{OUT}/{t}.csv', header=true, all_varchar=true)").fetchone()[0]
    print(f"  {t}.csv: {n} rows")
con.close()
