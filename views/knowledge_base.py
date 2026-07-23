"""Knowledge Base — the data-lineage explorer.

Walks the full chain and shows how each link holds:
University -> Semester -> Subject (NxtWave tag) -> Course (local name) -> Session
-> Scheduling -> Student Feedback -> Instructor Delivery, plus the content aligned
to it. Includes derived academic planning for every university and an alignment
panel that flags where links break (the delivered_niat<->delivered_sessions bridge
is fuzzy, ~76%). All read-only over existing tables + views.
"""
import streamlit as st

from aip import dashboard

CHAIN_DOT = """
digraph chain {
  rankdir=LR; bgcolor="transparent";
  node [shape=box style="rounded,filled" fillcolor="#f5f5f7" fontname="Helvetica" fontsize=10 color="#d0d0d0"];
  edge [fontname="Helvetica" fontsize=8 color="#888"];
  U   [label="University\\n× Semester" fillcolor="#ede7f6"];
  Sub [label="Subject\\n(NxtWave tag)" fillcolor="#e3f2fd"];
  C   [label="Course\\n(local name)" fillcolor="#e3f2fd"];
  Se  [label="Session\\nLECTURE · PRACTICE · EXAM"];
  I   [label="Instructor\\nDelivery" fillcolor="#fff3e0"];
  Sch [label="Scheduling\\n(delivered_sessions)"];
  Un  [label="Content unit\\nLP_RESOURCE · LP_QUIZ"];
  Cont[label="Content\\nreading · quiz · coding" fillcolor="#e3f2fd"];
  F   [label="Student\\nFeedback" fillcolor="#e8f5e9"];
  U -> Sub [label="subject_tags"];
  Sub -> C [label="nxtwave_tag"];
  C -> Se [label="course_title"];
  Se -> I [label="instructor_name"];
  Se -> Sch [label="fuzzy bridge · 85%\\n(no shared id)" style=dashed color="#d9534f" fontcolor="#d9534f"];
  Sch -> Un [label="session_id → unit_id"];
  Un -> Cont [label="unit_id"];
  Sch -> F [label="session_id"];
}
"""


def _uni_grid(colleges):
    """Clickable grid of universities; returns the selected institute_name."""
    if "kb_uni" not in st.session_state or st.session_state.kb_uni not in colleges:
        st.session_state.kb_uni = colleges[0]
    per_row = 4
    for i in range(0, len(colleges), per_row):
        cols = st.columns(per_row)
        for col, name in zip(cols, colleges[i:i + per_row]):
            if col.button(name, key=f"uni::{name}", width="stretch",
                          type="primary" if name == st.session_state.kb_uni else "secondary"):
                st.session_state.kb_uni = name
                st.rerun()
    return st.session_state.kb_uni


def _flag(pct):
    return "🟢" if pct >= 80 else "🟡" if pct >= 50 else "🔴"


def render():
    st.title("📚 Knowledge Base — Data Lineage")
    st.caption("The full chain, and how well each link holds. University → Subject → Course → "
               "Session (lecture/practice/exam) + Instructor → [85% fuzzy bridge] → Scheduling → "
               "Content unit (resource/quiz) → Content, with Feedback on the session.")
    con = dashboard.conn()

    try:
        st.graphviz_chart(CHAIN_DOT, width="stretch")
    except Exception:  # noqa: BLE001
        st.caption("University → Subject → Course → Session + Instructor → [85% bridge] → "
                   "Scheduling → Content unit → Content · Feedback")

    colleges = [r[0] for r in con.execute(
        "SELECT DISTINCT institute_name FROM college_summary ORDER BY 1").fetchall()]
    if not colleges:
        st.info("No colleges with delivery data found.")
        return
    uni = _uni_grid(colleges)
    sems = [r[0] for r in con.execute(
        "SELECT DISTINCT semester FROM delivered_niat WHERE institute_name=? AND semester IS NOT NULL ORDER BY 1",
        [uni]).fetchall()] or ["Semester 1"]
    sem = st.radio("Semester", sems, horizontal=True, key="kb_sem")
    st.divider()
    st.subheader(f"{uni} · {sem}")

    tabs = st.tabs(["Subjects → Content", "Courses → Sessions", "Instructor Delivery",
                    "Academic Planning", "Alignment", "Feedback"])

    # 1) SUBJECTS -> CONTENT : crosswalk (their name <-> tag) + content counts
    with tabs[0]:
        subs = con.execute("""
            WITH tc AS (
                SELECT tcm.nxtwave_tag,
                       count(*) FILTER (WHERE ca.kind='reading')        AS readings,
                       count(*) FILTER (WHERE ca.kind='objective')      AS objective,
                       count(*) FILTER (WHERE ca.kind='classroom_quiz') AS quiz,
                       count(*) FILTER (WHERE ca.kind='coding')         AS coding
                FROM tag_content_map tcm JOIN content_all ca ON ca.course = tcm.content_course
                GROUP BY 1),
            subj AS (   -- one row per subject; several local names can map to one tag,
                        -- so show the official (course_id-bearing) name as the label
                SELECT nxtwave_tag,
                       arg_max(university_course, CASE WHEN coalesce(course_id,'')<>'' THEN 1 ELSE 0 END) AS university_course,
                       arg_max(coalesce(credits,''), CASE WHEN coalesce(course_id,'')<>'' THEN 1 ELSE 0 END) AS credits
                FROM subject_tags WHERE institute_name = ? AND semester = ? GROUP BY nxtwave_tag)
            SELECT subj.university_course, subj.nxtwave_tag, subj.credits,
                   coalesce(tc.readings,0), coalesce(tc.objective,0),
                   coalesce(tc.quiz,0), coalesce(tc.coding,0)
            FROM subj LEFT JOIN tc ON tc.nxtwave_tag = subj.nxtwave_tag
            ORDER BY subj.university_course""", [uni, sem]).fetchall()
        if subs:
            st.markdown("**Their course name → NxtWave subject → content that belongs to it**")
            st.dataframe([{
                "Their course name": r[0], "NxtWave subject (tag)": r[1], "Credits": r[2],
                "Readings": r[3], "Objective": r[4], "Quiz": r[5], "Coding": r[6],
                "Content": "—" if (r[3]+r[4]+r[5]+r[6]) == 0 else "✓"} for r in subs],
                width="stretch", hide_index=True)
            st.caption("'—' = no content ingested for that subject yet.")
        else:
            st.info(f"No subject mapping on file for {uni} in {sem}.")

    # 2) COURSES -> SESSIONS : the chain rows (scheduling + feedback + instructor)
    with tabs[1]:
        courses = [r[0] for r in con.execute("""SELECT DISTINCT course_title FROM session_link
            WHERE institute_name = ? AND semester = ? AND is_curriculum(course_title)
            ORDER BY 1""", [uni, sem]).fetchall()]
        if not courses:
            st.info(f"No delivered courses for {uni} in {sem}.")
        else:
            course = st.selectbox("Course", courses, key="kb_course")
            total = con.execute("""SELECT count(*) FROM session_link
                WHERE institute_name=? AND semester=? AND course_title=? AND is_scheduled""",
                [uni, sem, course]).fetchone()[0]
            rows = con.execute("""
                SELECT sl.session_title, sl.session_type, sl.instructor_name, sl.session_status,
                       sl.start_ts, sl.section_name, sl.linked,
                       f.teaching_quality_rating, (sl.unit_id IS NOT NULL) AS has_unit
                FROM session_link sl
                LEFT JOIN session_feedback_safe f
                       ON f.session_id = sl.session_id AND f.institute_name = sl.institute_name
                WHERE sl.institute_name=? AND sl.semester=? AND sl.course_title=? AND sl.is_scheduled
                ORDER BY sl.start_ts LIMIT 200""", [uni, sem, course]).fetchall()
            st.caption(f"{total:,} scheduled sessions in {course} — showing first {len(rows)}. "
                       "'Linked' = this session was matched to the scheduling data.")
            st.dataframe([{
                "Session": r[0], "Type": r[1], "Instructor": r[2] or "—", "Status": r[3] or "—",
                "When": str(r[4])[:16], "Section": r[5], "Linked": "✓" if r[6] else "✗",
                "Teaching rating": r[7] or "—", "Content": "✓" if r[8] else "—"}
                for r in rows], width="stretch", hide_index=True)

    # 3) INSTRUCTOR DELIVERY : per-instructor stats, derived from the chain (session_link)
    with tabs[2]:
        instr = con.execute("""SELECT instructor_name, any_value(instructor_category) AS cat,
                count(*) FILTER (WHERE is_scheduled)                          AS sessions,
                count(DISTINCT course_title)                                 AS courses,
                round(100.0 * count(*) FILTER (WHERE session_status='COMPLETED')
                      / nullif(count(*) FILTER (WHERE is_scheduled), 0), 0)  AS pct_completed
            FROM session_link
            WHERE institute_name=? AND semester=? AND instructor_name IS NOT NULL
            GROUP BY 1 ORDER BY sessions DESC""", [uni, sem]).fetchall()
        if instr:
            tot = sum(r[2] for r in instr)
            done = sum((r[4] or 0) * r[2] for r in instr)
            k = st.columns(3)
            k[0].metric("Instructors", len(instr))
            k[1].metric("Sessions", f"{tot:,}")
            k[2].metric("Avg completion", f"{round(done / tot) if tot else 0}%")
            st.dataframe([{
                "Instructor": r[0], "Category": r[1] or "—", "Sessions": r[2],
                "Courses": r[3], "Completion %": r[4]} for r in instr],
                width="stretch", hide_index=True)
            st.caption("Derived from the chain (session_link) for this university & semester. "
                       "Low completion may reflect scheduling, not the instructor.")
        else:
            st.info("No instructor data for this selection "
                    "(the instructor table covers NIAT-tracked delivery).")

    # 4) ACADEMIC PLANNING : derived (all unis) + designed (the 4)
    with tabs[3]:
        st.markdown("**Derived from delivery** (available for every university). "
                    "*Sessions/section* = lecture (teaching) sessions per section — the same basis "
                    "as the plan below, so a course's number matches across both tables.")
        dp = con.execute("""SELECT course_title, sessions_per_section, teaching_weeks,
                first_session, last_session, start_slip_days, pct_completed
            FROM academic_plan_derived WHERE institute_name=? AND semester=?
            ORDER BY scheduled_sessions DESC""", [uni, sem]).fetchall()
        if dp:
            st.dataframe([{
                "Course": r[0], "Sessions/section": r[1], "Teaching weeks": r[2],
                "First": str(r[3]), "Last": str(r[4]), "Start slip (days)": r[5],
                "Completion %": r[6]} for r in dp], width="stretch", hide_index=True)
        else:
            st.info("No delivery to derive planning from for this selection.")
        # Designed plan with a REASON for each planned course instead of a bare
        # "not matched". If a planned course isn't matched to delivery by name, find its
        # real delivered counterpart via the shared subject tag, or a near-identical name
        # (typo). So each row reads "delivered as 'X'" or an honest "not delivered".
        # Designed data is Semester 1 only.
        designed = con.execute("""
            WITH plan AS (
                SELECT course, planned_sessions, planned_total_hours, planned_weeks, coverage,
                       actual_lectures_per_section,
                       course_key_loose(course) AS pk,
                       (SELECT st.nxtwave_tag FROM subject_tags st
                        WHERE st.institute_name=? AND st.semester='Semester 1'
                          AND (course_key(st.university_course)=course_key(course_plan_vs_actual.course)
                               OR course_key(st.nxtwave_tag)=course_key(course_plan_vs_actual.course)) LIMIT 1) AS tag
                FROM course_plan_vs_actual
                WHERE university IN (SELECT code FROM universities WHERE institute_name=?)
                  AND coverage <> 'delivered_not_planned'
            ),
            cand AS (
                SELECT DISTINCT d.course_title,
                       (SELECT st.nxtwave_tag FROM subject_tags st
                        WHERE st.institute_name=d.institute_name AND st.semester=d.semester
                          AND course_key(st.university_course)=course_key(d.course_title) LIMIT 1) AS tag,
                       course_key_loose(d.course_title) AS dk
                FROM delivered_niat d
                WHERE d.institute_name=? AND d.semester='Semester 1' AND is_curriculum(d.course_title)
            )
            SELECT plan.course, plan.planned_sessions, plan.planned_total_hours, plan.planned_weeks,
                   plan.coverage, plan.actual_lectures_per_section,
                   (SELECT c.course_title FROM cand c WHERE c.tag=plan.tag AND plan.tag IS NOT NULL LIMIT 1) AS as_tag,
                   (SELECT c.course_title FROM cand c ORDER BY jaro_winkler_similarity(c.dk, plan.pk) DESC LIMIT 1) AS as_fuzzy,
                   (SELECT max(jaro_winkler_similarity(c.dk, plan.pk)) FROM cand c) AS sim
            FROM plan ORDER BY plan.planned_sessions DESC NULLS LAST
        """, [uni, uni, uni]).fetchall()
        if designed and sem == "Semester 1":
            # actual lecture-sessions/section per delivered course, so we can show the gap
            # even for courses delivered under a different name.
            actual_map = dict(con.execute("""SELECT course, sum(actual_lectures_per_section)
                FROM course_plan_vs_actual
                WHERE university IN (SELECT code FROM universities WHERE institute_name=?)
                  AND actual_lectures_per_section IS NOT NULL GROUP BY course""", [uni]).fetchall())
            from collections import OrderedDict
            agg = OrderedDict()  # one row per planned course; sum actual across multi-matches (lecture + lab)
            for course, planned, hrs, weeks, cov, actual_self, as_tag, as_fuzzy, sim in designed:
                d = agg.setdefault(course, {"planned": planned, "hrs": hrs, "weeks": weeks, "cov": cov,
                                            "actual": 0.0, "as_tag": as_tag, "as_fuzzy": as_fuzzy, "sim": sim})
                if actual_self is not None:
                    d["actual"] += actual_self
            table = []
            for course, d in agg.items():
                if d["cov"] == "both":
                    delivery, actual = "✓ delivered", d["actual"]
                elif d["as_tag"]:
                    delivery, actual = f"delivered as '{d['as_tag']}'", actual_map.get(d["as_tag"])
                elif d["sim"] is not None and d["sim"] >= 0.90:
                    delivery, actual = f"delivered as '{d['as_fuzzy']}' (name differs)", actual_map.get(d["as_fuzzy"])
                else:
                    delivery, actual = "not delivered", None
                planned = d["planned"]
                gap = (round(actual) - round(planned)) if (actual and planned is not None) else None
                table.append({
                    "Course": course, "Planned sessions": round(planned) if planned is not None else "—",
                    "Planned hrs": d["hrs"], "Planned weeks": d["weeks"], "Delivery": delivery,
                    "Actual/section": round(actual, 1) if actual else "—",
                    "Gap": (f"{gap:+d}" if gap is not None else "—")})
            st.markdown("**Designed plan** (HLID — Semester 1). Each row is a planned course; "
                        "**Delivery** explains how it ran and **Gap** is actual − planned sessions/section.")
            st.dataframe(table, width="stretch", hide_index=True)
            st.caption("**Delivery** — ✓ delivered (same name) · *delivered as '…'* (same subject, different "
                       "name) · *not delivered*. **Actual/section** = lecture sessions delivered per section; "
                       "**Gap** = actual − planned (+ over-delivered, − under).")
        elif designed and sem != "Semester 1":
            st.caption("ℹ️ Designed-plan (HLID) comparison is available for **Semester 1 only** — designed "
                       "data covers Sem 1. The derived-from-delivery table above still applies to this semester.")

    # 5) ALIGNMENT : how well each link in the chain holds
    with tabs[4]:
        st.markdown("**How well the chain links up for this university & semester**")
        # course -> tag coverage
        cov = con.execute("""
            WITH courses AS (SELECT DISTINCT course_title FROM session_link
                             WHERE institute_name=? AND semester=? AND is_curriculum(course_title)),
                 tagged AS (SELECT DISTINCT university_course FROM subject_tags
                            WHERE institute_name=? AND semester=?)
            SELECT (SELECT count(*) FROM courses) c,
                   (SELECT count(*) FROM courses WHERE course_key(course_title)
                        IN (SELECT course_key(university_course) FROM tagged)) t
            """, [uni, sem, uni, sem]).fetchone()
        link = con.execute("""SELECT count(*) FILTER (WHERE is_scheduled),
                count(*) FILTER (WHERE is_scheduled AND linked),
                count(*) FILTER (WHERE is_scheduled AND instructor_name IS NOT NULL)
            FROM session_link WHERE institute_name=? AND semester=?""", [uni, sem]).fetchone()
        fb = con.execute("""SELECT count(*) FILTER (WHERE sl.is_scheduled AND sl.session_id IS NOT NULL),
                count(DISTINCT sl.session_id) FILTER (WHERE f.session_id IS NOT NULL)
            FROM session_link sl LEFT JOIN session_feedback_safe f
                 ON f.session_id=sl.session_id AND f.institute_name=sl.institute_name
            WHERE sl.institute_name=? AND sl.semester=?""", [uni, sem]).fetchone()

        def pct(n, d):
            return round(100 * n / d) if d else 0
        sched = link[0] or 1
        checks = [
            ("Subject ↔ Course", pct(cov[1], cov[0]), f"{cov[1]}/{cov[0]} delivered courses tagged"),
            ("Session ↔ Scheduling", pct(link[1], sched), f"{link[1]:,}/{sched:,} sessions linked to scheduling/units (fuzzy bridge)"),
            ("Session ↔ Instructor", pct(link[2], sched), f"{link[2]:,}/{sched:,} sessions have a named instructor"),
            ("Session ↔ Feedback", pct(fb[1], fb[0] or 1), f"{fb[1]:,}/{fb[0]:,} linkable sessions have feedback"),
        ]
        for label, p, detail in checks:
            c1, c2 = st.columns([1, 3])
            c1.metric(label, f"{_flag(p)} {p}%")
            c2.caption(detail)
        prec = con.execute("""SELECT link_precision, count(*) FROM session_link
            WHERE institute_name=? AND semester=? AND is_scheduled GROUP BY 1""", [uni, sem]).fetchall()
        pm = {p: n for p, n in prec}
        st.caption(f"Bridge confidence — same time (high): {pm.get('minute', 0):,} · "
                   f"same day (fallback): {pm.get('day', 0):,} · unmatched: {pm.get('none', 0):,}. "
                   "delivered_niat and delivered_sessions share no key; this is the known break.")

        # why-unmatched diagnostic: is the gap a time mismatch, or a scope/naming gap?
        if pm.get("none"):
            diag = con.execute("""
                WITH un AS (SELECT lower(trim(session_title)) t FROM session_link
                            WHERE institute_name=? AND semester=? AND is_scheduled AND NOT linked),
                     titles AS (SELECT DISTINCT lower(trim(session_title)) t
                                FROM delivered_sessions WHERE institute_name=?)
                SELECT count(*), count(*) FILTER (WHERE t IN (SELECT t FROM titles)) FROM un
                """, [uni, sem, uni]).fetchone()
            tot_un, time_mismatch = diag[0], diag[1]
            not_found = tot_un - time_mismatch
            with st.expander(f"Why {tot_un:,} sessions didn't link"):
                st.write(f"- **{time_mismatch:,} ({round(100*time_mismatch/tot_un)}%)** — title exists in the "
                         "scheduling data but at a different time (a time/section mismatch).")
                st.write(f"- **{not_found:,} ({round(100*not_found/tot_un)}%)** — title not in the scheduling data "
                         "at all: the two delivery exports cover different scopes (delivered_niat is broader "
                         "than the unit-linked Clickup sessions), or the title differs. Not a bug — a data-scope gap.")

    # 6) FEEDBACK — scoped to this semester via session_link (feedback itself has no
    # semester column; its session_id places it in a semester). IN-subquery avoids the
    # row duplication a direct join would cause when a session_id fuzzy-matches twice.
    with tabs[5]:
        sem_sessions = """(SELECT DISTINCT session_id FROM session_link
                           WHERE institute_name=? AND semester=? AND session_id IS NOT NULL)"""
        agg = con.execute(f"""SELECT count(*), round(avg(TRY_CAST(session_understanding_rating AS DOUBLE)),2),
                round(avg(TRY_CAST(teaching_quality_rating AS DOUBLE)),2)
            FROM session_feedback_safe WHERE institute_name=?
              AND session_id IN {sem_sessions}""", [uni, uni, sem]).fetchone()
        if agg and agg[0]:
            f = st.columns(3)
            f[0].metric("Rated sessions", f"{agg[0]:,}")
            f[1].metric("Avg understanding", agg[1])
            f[2].metric("Avg teaching", agg[2])
            low = con.execute(f"""SELECT session_title, teaching_quality_rating, total_feedbacks
                FROM session_feedback_safe WHERE institute_name=?
                AND session_id IN {sem_sessions}
                AND TRY_CAST(teaching_quality_rating AS DOUBLE) IS NOT NULL
                ORDER BY TRY_CAST(teaching_quality_rating AS DOUBLE) LIMIT 10""", [uni, uni, sem]).fetchall()
            st.markdown("**Lowest-rated sessions**")
            st.dataframe([{"Session": r[0], "Teaching": r[1], "Feedbacks": r[2]} for r in low],
                         width="stretch", hide_index=True)
            st.caption(f"Student feedback for {sem} (placed via the session's scheduling link).")
        else:
            st.info(f"No feedback recorded for {uni} in {sem}.")
