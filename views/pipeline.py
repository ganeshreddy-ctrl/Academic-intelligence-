"""Pipeline page — visualise the data pipeline and its current output.

Shows the flow (raw exports -> build scripts -> canonical -> DuckDB -> agent), live
row counts per table/view, and the per-course content-ingestion inventory. Visualises
the current committed state; it does not re-run ingestion (raw files are gitignored and
absent on Streamlit Cloud).
"""
import streamlit as st

from aip import dashboard

# What each build script produces -> which tables. Raw files aren't present on Cloud,
# so this manifest documents the sources; counts come from the live DB.
STAGES = [
    ("build_operational.py", "Clickup scheduling + feedback (xlsx)", ["sessions", "session_feedback", "instructor_sessions"]),
    ("build_delivered.py",   "Clickup scheduled sessions (csv)",     ["delivered_sessions", "delivered_niat"]),
    ("build_designed.py",    "HLID + Prod Sequence (xlsx)",          ["designed_sequence", "designed_course_plan"]),
    ("build_content.py",     "Course content exports (xlsx/json)",   ["course_content"]),
    ("build_issues.py",      "RCA / issues board (xlsx)",            ["issues"]),
    ("build_course_crosswalk.py", "Course catalogue + delivered names", ["course_crosswalk"]),
]

DOT = """
digraph pipeline {
  rankdir=LR; node [shape=box style="rounded,filled" fillcolor="#f5f5f7" fontname="Helvetica" fontsize=11];
  raw   [label="Raw exports\\n(xlsx / json)" fillcolor="#fff3e0"];
  build [label="build_*.py\\nscripts"];
  canon [label="Canonical\\nCSV / parquet"];
  duck  [label="load_duckdb.py\\n→ tables + views" fillcolor="#e3f2fd"];
  agent [label="Copilot agent\\n(read-only SQL)" fillcolor="#e8f5e9"];
  raw -> build -> canon -> duck -> agent;
}
"""


def render():
    st.title("🔧 Pipeline")
    st.caption("How raw exports become the data the copilot answers from. "
               "Rebuilt from committed data on every deploy — this reflects the current state.")

    try:
        st.graphviz_chart(DOT, width="stretch")
    except Exception:  # noqa: BLE001 - fall back to a plain stage strip if graphviz is unavailable
        cols = st.columns(5)
        for c, label in zip(cols, ["Raw exports", "build_*.py", "Canonical files",
                                   "DuckDB tables + views", "Copilot agent"]):
            c.info(label)

    counts = dict(dashboard.table_counts())

    st.subheader("Sources → tables")
    st.dataframe(
        [{"Build script": s, "Source": src,
          "Produces": ", ".join(t), "Rows": f"{sum(counts.get(t2, 0) for t2 in t):,}"}
         for s, src, t in STAGES],
        width="stretch", hide_index=True)

    st.subheader("DuckDB tables & views")
    con = dashboard.conn()
    views = {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_type='VIEW'").fetchall()}
    st.dataframe(
        [{"Name": n, "Kind": "view" if n in views else "table", "Rows": f"{c:,}"}
         for n, c in sorted(counts.items())],
        width="stretch", hide_index=True)
    total = sum(counts.values())
    st.caption(f"{len(counts)} tables/views · {total:,} rows total")

    st.subheader("Content ingested (per course)")
    inv = con.execute("""SELECT course,
            count(*) FILTER (WHERE kind='reading')        AS readings,
            count(*) FILTER (WHERE kind='objective')      AS objective,
            count(*) FILTER (WHERE kind='classroom_quiz') AS classroom_quiz,
            count(*) FILTER (WHERE kind='coding')         AS coding,
            count(*) AS total
        FROM course_content GROUP BY 1 ORDER BY total DESC""").fetchall()
    st.dataframe(
        [{"Course": r[0], "Readings": r[1], "Objective": r[2],
          "Classroom quiz": r[3], "Coding": r[4], "Total": r[5]} for r in inv],
        width="stretch", hide_index=True)
    st.caption(f"{len(inv)} courses ingested into course_content.")
