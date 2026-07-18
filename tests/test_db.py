#!/usr/bin/env python3
"""Checks for the SQL guardrail and the data conversions.

The guardrail is a trust boundary — run_sql takes model-generated text — so it
gets real coverage. The conversions get coverage because a silent Excel-serial
bug already produced a planned_start in 2064 once.

Run: python tests/test_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aip import db

con = db.connect()
fails = []


def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except AssertionError as e:
        fails.append(name)
        print(f"  FAIL  {name}: {e}")


def rejects(sql):
    try:
        db.run_sql(sql, con)
    except db.QueryError:
        return
    raise AssertionError(f"should have been rejected: {sql!r}")


print("guardrail:")
check("rejects INSERT", lambda: rejects("INSERT INTO courses VALUES (1)"))
check("rejects UPDATE", lambda: rejects("UPDATE courses SET stack='x'"))
check("rejects DELETE", lambda: rejects("DELETE FROM courses"))
check("rejects DROP", lambda: rejects("DROP TABLE courses"))
check("rejects CREATE", lambda: rejects("CREATE TABLE t AS SELECT 1"))
check("rejects ATTACH", lambda: rejects("ATTACH 'x.db'"))
check("rejects COPY (exfiltration)", lambda: rejects("COPY courses TO '/tmp/x.csv'"))
check("rejects multi-statement", lambda: rejects("SELECT 1; DROP TABLE courses"))
check("rejects empty", lambda: rejects("   "))


def allows_select():
    cols, rows, trunc = db.run_sql("SELECT count(*) AS n FROM courses", con)
    assert rows[0][0] == 63, f"expected 63 courses, got {rows[0][0]}"


def enforces_row_cap():
    _, rows, trunc = db.run_sql("SELECT * FROM delivered_sessions", con)
    assert len(rows) == db.ROW_LIMIT, f"expected cap at {db.ROW_LIMIT}, got {len(rows)}"
    assert trunc is True, "truncation flag not set"


check("allows SELECT", allows_select)
check("enforces row cap + truncation flag", enforces_row_cap)

print("\ndata:")


def mrv_sem1():
    _, rows, _ = db.run_sql("""SELECT count(*) FROM delivered_sessions
        WHERE institute_name='Malla Reddy Vishwavidyapeeth' AND semester='Semester 1'""", con)
    assert rows[0][0] == 7702, f"expected 7702 MRV Sem-1 rows, got {rows[0][0]}"


def timestamps_are_real():
    _, rows, _ = db.run_sql("""SELECT count(*) FROM delivered_sessions
        WHERE start_ts < '2024-01-01' OR start_ts > '2027-01-01'""", con)
    assert rows[0][0] == 0, f"{rows[0][0]} rows with implausible timestamps (serial conversion)"


def planned_start_sane():
    _, rows, _ = db.run_sql("""SELECT count(*) FROM deviation
        WHERE planned_start IS NOT NULL
          AND (planned_start < '2025-01-01' OR planned_start > '2026-12-31')""", con)
    assert rows[0][0] == 0, f"{rows[0][0]} units with planned_start outside 2025-26 (week col is a date?)"


def deviation_scoped_to_designed_unis():
    _, rows, _ = db.run_sql("SELECT count(*) FROM deviation WHERE university IS NULL", con)
    assert rows[0][0] == 0, f"{rows[0][0]} deviation rows with no university — view is leaking institutes"


def planning_knowledge_present():
    """The agent's planning ability depends on these reference tables existing."""
    _, r1, _ = db.run_sql("SELECT count(*) FROM scheduling_rules", con)
    assert r1[0][0] == 11, f"expected 11 scheduling rules, got {r1[0][0]}"
    _, r2, _ = db.run_sql("SELECT count(*) FROM planning_standards", con)
    assert r2[0][0] >= 14, f"planning_standards missing rows: {r2[0][0]}"


def issues_join_to_institutes():
    """Recorded issues must join to delivery on institute_name (not the short code)."""
    _, r, _ = db.run_sql("""SELECT count(DISTINCT i.institute_name)
        FROM issues i WHERE i.institute_name IN (SELECT institute_name FROM delivered_niat)""", con)
    assert r[0][0] >= 3, f"issues not joining to delivered institutes: {r[0][0]}"


def feedback_safe_hides_comments():
    cols, _, _ = db.run_sql("SELECT * FROM session_feedback_safe LIMIT 1", con)
    leaked = [c for c in cols if "feedbacks" in c.lower() and c != "total_feedbacks"]
    assert not leaked, f"comment text leaked into the agent-facing view: {leaked}"


def submodules_not_double_counted():
    """MRV's HLID lists Web App Dev-1 (75 sessions) AND its 4 parts (28+15+17+15=75).

    Summing every row gives 593 hrs instead of 460 (+29%) and turns a 93%-utilised
    plan into a fictional 120% overload. The agent made exactly this error.
    """
    _, rows, _ = db.run_sql("""SELECT round(sum(planned_total_hours),0)
        FROM course_plan_vs_actual WHERE university='MRV'""", con)
    assert rows[0][0] == 460, f"expected MRV planned total 460 hrs, got {rows[0][0]} (sub-module double-count?)"


def plan_vs_actual_finds_unplanned_courses():
    """MRV delivered Intro to NIAT / Test Your Current Knowledge / Foreign Language,
    none of which are in its HLID. The FULL OUTER join must surface them."""
    _, rows, _ = db.run_sql("""SELECT count(*) FROM course_plan_vs_actual
        WHERE university='MRV' AND coverage='delivered_not_planned'""", con)
    assert rows[0][0] == 3, f"expected 3 delivered-but-not-planned MRV courses, got {rows[0][0]}"


check("MRV Semester 1 = 7702 rows", mrv_sem1)
check("sub-modules not double-counted (MRV = 460 hrs, not 593)", submodules_not_double_counted)
check("plan_vs_actual surfaces delivered-but-unplanned courses", plan_vs_actual_finds_unplanned_courses)
check("delivered timestamps are plausible", timestamps_are_real)
check("deviation planned_start within 2025-26", planned_start_sane)
check("deviation covers only designed universities", deviation_scoped_to_designed_unis)
check("scheduling_rules + planning_standards present", planning_knowledge_present)
check("recorded issues join to institutes", issues_join_to_institutes)
check("session_feedback_safe excludes comment text", feedback_safe_hides_comments)

con.close()
print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all checks passed")
