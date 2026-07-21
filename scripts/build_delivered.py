#!/usr/bin/env python3
"""Flatten raw Clickup scheduling into committed, queryable 'delivered' tables.

Writes:
  data/canonical/delivery/delivered_sessions.parquet  — unit-level: what ran, when, which unit
  data/canonical/delivery/delivered_niat.parquet      — course/instructor/status level

These are two SEPARATE tables on purpose: the NIAT export carries no unit_id or
session_id, so it cannot be joined to the unit-level export on any key. Its
datetimes are also unreliable (see below). Forcing a composite join on
(institute, title, timestamp) would silently fabricate links — we don't.

Parquet not CSV: ~400K rows would be a ~50MB CSV; parquet is a few MB, keeps
types (no Excel-serial reparsing downstream), and DuckDB reads it natively.
That matters on a 1GB Streamlit Cloud box.

Usage: python scripts/build_delivered.py
"""
import duckdb, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

S = "data/raw/delivery"
OUT = "data/canonical/delivery"
os.makedirs(OUT, exist_ok=True)
con = duckdb.connect()
rd = lambda f: f"read_csv_auto('{S}/{f}', header=true, all_varchar=true, ignore_errors=true)"

# Excel serial -> timestamp. Epoch 1899-12-30. Raw serials must never reach the agent.
def serial(col):
    return f"TIMESTAMP '1899-12-30' + INTERVAL (CAST({col} AS DOUBLE)) DAY"

# The NIAT export mixes three datetime encodings in one column:
#   - Excel serial  ('46046.395833')            -> 94,765 rows
#   - text w/ non-standard month ('23 Sept 2025, 15:30:00') -> 9,094 rows ('Sept', not 'Sep')
#   - '-' placeholder for never-scheduled sessions          -> 53,641 rows
# ponytail: a CASE covers all three; '-' becomes NULL and is_scheduled=false rather
# than being silently dropped, because "planned but never scheduled" is a real answer.
def niat_ts(col):
    return f"""CASE
        WHEN TRY_CAST({col} AS DOUBLE) IS NOT NULL
          THEN {serial(f'TRY_CAST({col} AS DOUBLE)')}
        ELSE TRY_STRPTIME(replace({col}, 'Sept', 'Sep'), '%d %b %Y, %H:%M:%S')
      END"""

# 1) delivered_sessions — unit-level truth: session -> unit, with real timestamps.
#    batch_section_name is a COMMA-SEPARATED LIST of sections ("TU Batch-1-S-002, TU Batch-1-S-003").
#    Kept raw here; load_duckdb.py exposes an exploded `delivered_sections` view.
con.execute(f"""COPY (
  SELECT
    institute_name,
    batch_section_name,
    derived_semester_title             AS semester,
    session_id,
    session_title,
    session_type,
    unit_id,
    resource_type,
    {serial('session_start_datetime')} AS start_ts,
    {serial('session_end_datetime')}   AS end_ts
  FROM {rd('scheduled-session-details.csv')}
  WHERE trim(coalesce(session_id,'')) <> ''
) TO '{OUT}/delivered_sessions.parquet' (FORMAT PARQUET)""")

# 2) delivered_niat — course / instructor / status. No unit_id, no session_id: standalone.
con.execute(f"""COPY (
  SELECT
    "Institute Name"      AS institute_name,
    "Batch Name"          AS batch_name,
    "Section Name"        AS section_name,
    "Semester Title"      AS semester,
    "Course Title"        AS course_title,
    "Session Title"       AS session_title,
    "Session Type"        AS session_type,
    nullif("Session Status",'-')       AS session_status,
    nullif("Instructor Name",'-')      AS instructor_name,
    nullif("Instructor Category",'-')  AS instructor_category,
    TRY_CAST("Week Count" AS DOUBLE)   AS week_count,
    nullif("Week Status",'-')          AS week_status,
    {niat_ts('"Session Start DateTime"')} AS start_ts,
    {niat_ts('"Session End DateTime"')}   AS end_ts,
    ({niat_ts('"Session Start DateTime"')} IS NOT NULL) AS is_scheduled
  FROM {rd('niat-scheduled-session-details.csv')}
  WHERE nullif(trim("Institute Name"), '') IS NOT NULL   -- drop trailing empty export rows
) TO '{OUT}/delivered_niat.parquet' (FORMAT PARQUET)""")

for t in ["delivered_sessions", "delivered_niat"]:
    n = con.execute(f"SELECT count(*) FROM read_parquet('{OUT}/{t}.parquet')").fetchone()[0]
    mb = os.path.getsize(f"{OUT}/{t}.parquet") / 1e6
    print(f"  {t}.parquet: {n} rows, {mb:.1f} MB")

# self-check: the conversions are the whole point of this script, so verify them.
bad = con.execute(f"""SELECT count(*) FROM read_parquet('{OUT}/delivered_sessions.parquet')
                      WHERE start_ts < TIMESTAMP '2024-01-01' OR start_ts > TIMESTAMP '2027-01-01'""").fetchone()[0]
assert bad == 0, f"{bad} delivered_sessions rows have implausible timestamps — serial conversion is wrong"

sched, unsched = con.execute(f"""SELECT count(*) FILTER (WHERE is_scheduled),
                                        count(*) FILTER (WHERE NOT is_scheduled)
                                 FROM read_parquet('{OUT}/delivered_niat.parquet')""").fetchone()
print(f"  delivered_niat: {sched} scheduled, {unsched} never-scheduled ('-' placeholders)")
assert unsched > 50000, "expected ~53.6K unscheduled placeholder rows; parse may have changed"
con.close()
