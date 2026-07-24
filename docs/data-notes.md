# Data notes — what the schema cannot tell you

Injected verbatim into the agent's prompt, alongside the live schema. Everything here
is a thing that will produce a confidently wrong answer if ignored.

**Use all the data.** The store has ~29 tables/views across delivery, feedback, content,
planning, subjects, and issues. Answer from every layer that bears on the question — don't
report from one table when another adds essential context (e.g. a pacing answer that ignores
feedback and recorded issues is half an answer). For planning requests, the full output
contract is in `planning-method.md`.

## Join-key contract

- **`unit_id` is the universal key.** It links content, delivered, designed, and feedback. Prefer it over anything else.
- **`session_id` is stored dash-less** (32-hex) in `sessions`, `delivered_sessions`, and `session_feedback`. Never join on a dashed UUID.
- **Course titles do NOT join across layers.** Delivered has ~148 titles, the catalogue has 63, and the names differ. Use `course_crosswalk` (`raw_title` → `catalogue_course_title`, via normalized `course_key`). A course-level count taken without the crosswalk is wrong. Coverage: a curated alias table (`match_status='alias'`, from `course_alias.csv`) patches the high-volume title variants and typos, so **~92% of Sem-1 delivered session volume now maps** (was ~50%). What remains `unmapped` is genuine non-curriculum or non-CS content — assessments, orientation ("Introduction to NIAT"), Basic Electronics, Physics/Chemistry — which have no catalogue course by design, not a bug.
- **There is no Subject entity.** `courses.stack` (11 stacks) is the closest roll-up.
- **`delivered_niat` cannot be joined to `delivered_sessions`.** It carries no `unit_id` and no `session_id`. Use it standalone for instructor / course-title / session-status questions. Do not invent a join on title+timestamp.
- **A session's `session_type` is only LECTURE / PRACTICE / EXAM.** "Quiz" is NOT a session type — it is a **content unit** (`delivered_sessions.resource_type='LP_QUIZ'`, or `course_content.kind='classroom_quiz'`), one level below the session (a session holds ~2 units). So "how many quiz *sessions*" is a category error; answer quiz questions from units/content, and lecture/practice/exam counts from `session_type`.

## Current data scope & linkage health (know this before answering coverage questions)
- **Universities:** 17 real (in `college_summary`), all subject-mapped. Delivery spans **Semesters 1–4**; the subjects sheet (`subject_tags`) is **1st-year only (Sem 1+2)**, so Sem-3/4 courses are largely untagged.
- **Subjects:** 20 canonical `nxtwave_tag`s. **Designed HLID plans:** 16 universities in `course_plan_vs_actual` (**code `NIATCH` = NIAT Chevella**). Derived planning (`academic_plan_derived`) covers all 17.
- **Content:** ingested (`course_content`) for ~13 course names; catalogue (`reading/objective/coding/editorials`) for ~15. **Editorials** = DSA coding-question solutions, in `content_all` as `kind='editorial'`. **Feedback:** 6,945 rated sessions (empties removed; every row has a `session_id`).
- **Known linkage gaps — caveat these in answers:** Session→Scheduling links **~85%** (fuzzy bridge; 15% unmatched). Only **~70%** of delivered curriculum courses map to a subject (mostly Sem-3/4). Content exists for a minority of delivered units. 8 subjects have no content yet. Absence usually means *not covered/ingested*, not *zero*.
- **Semester scope — the product is Sem 1-2; Sem 3/4 are OUT OF SCOPE.** Sem 1-2 have delivery + feedback (`session_feedback_safe`, mapped via `delivered_sessions`) + subjects (`subject_tags`); **designed** plans (`course_plan_vs_actual` / `designed_sequence` / `deviation`) are **Sem 1 only**. Sem 3 has raw `delivered_niat` rows but **no feedback, content, subjects, or designed plan**; **Sem-4 delivery is the internal NIAT entity only** (no partner college). `college_summary` and the Knowledge Base are **scoped to Sem 1-2**. **Do not plan or analyse Sem 3/4** — if asked, say they're out of scope (delivery exists, but the supporting layers don't). (A stray Jun–Jul 2026 tail of ~5k sessions can skew min/max date windows; prefer explicit semester filters.)

## Table meanings and grain

| Table | Grain | Notes |
|---|---|---|
| `delivered_sessions` | one row per session×unit scheduled | What actually ran. `start_ts`/`end_ts` are real timestamps. Sem 1 **and** Sem 2. |
| `delivered_sections` | `delivered_sessions` exploded by section | `batch_section_name` is a **comma-separated list** ("TU Batch-1-S-002, TU Batch-1-S-003"); one row can cover several sections. Use this view for per-section questions — counting `batch_section_name` counts section *groupings*, not sections. |
| `delivered_niat` | one row per planned session | Has course/instructor/status. **34% (53,643 rows) were never scheduled** — `is_scheduled = false`, `start_ts` null. Filter on `is_scheduled` or you will count sessions that never happened. |
| `designed_sequence` | one row per unit per sheet | The plan (HLID/Prod). **Semester 1 only.** May contain the same `unit_id` more than once (MRV has a "NEW BATCH" re-plan alongside the original) — dedupe by `unit_id` when counting. |
| `designed_course_plan` | one row per university×course | HLID "Student Journey": planned session counts, hours, start/end timelines. Sem 1 block only. **`is_submodule='True'` rows are components of the course above them — ALWAYS exclude them from any total** (see below). |
| `deviation` | one row per university×unit | Pre-solved designed↔delivered join. Use this rather than re-deriving it. |
| `session_link` | one row per delivered_niat session | **The bridge between the two delivery tables.** `delivered_niat` (course + instructor + status) has no session_id/unit_id; `delivered_sessions` (session_id + unit_id + feedback link) has no course/instructor. This LEFT JOINs them on institute + session_title + start-minute, adding `session_id`, `unit_id`, and a `linked` flag (~76% match). Use it to connect a course/instructor session to its scheduling, feedback (by session_id), and content (by unit_id). Unmatched rows have `linked=false` — the gap is real, not hidden. |
| `academic_plan_derived` | one row per (institute, semester, course) | **Planning-style metrics derived from delivery, for ALL universities** (designed plans exist for 16). `sessions_per_section` counts **lecture (teaching) sessions** per section — the same basis as the HLID's planned session count (planned ≈ lectures), so it matches `course_plan_vs_actual.actual_lectures_per_section`; also teaching_weeks, first/last_session, start_slip_days, pct_completed. This is the universal "plan" layer; `course_plan_vs_actual` is the real *designed* plan for the 16 with HLID/Prod data. |
| `college_summary` | one row per college × **semester** | **At-a-glance health per college** — sections, courses, scheduled_sessions, pct_completed, teaching_weeks, first/last_session, avg_understanding, avg_teaching, recorded_issues, has_designed_plan. Use for "how is X doing", "compare colleges", "which college is struggling". Covers **Sem 1-2** (Sem 3/4 out of scope — no feedback/content/designed data; Sem 4 is the internal NIAT entity only) — filter `WHERE semester=…` for one. `has_designed_plan` true only for Sem 1. |
| `course_plan_vs_actual` | one row per university×course | **Pre-solved plan-vs-delivery, already per-section.** Use this for any "how did the plan hold up / give me a better plan" question. |

## ⚠️ `designed_course_plan.is_submodule` — read before summing anything

The HLID lists a course **and then its component modules as sibling rows**. For MRV: `Web Application Development-1` (75 sessions) is followed by `Build Your own Static Website` (28) + `Build Your own Responsive Website` (15) + `Modern Responsive Web Design` (17) + `Build Your Own Dynamic Web Application` (15) — which sum to exactly 75. **They are the same sessions listed twice.**

Summing every row inflates MRV's Sem-1 load from **460 hrs to 593 (+29%)**, turning a sensible 93%-utilised plan into a fictional 120% overload — and every recommendation built on that is wrong. Always filter `WHERE is_submodule <> 'True'`, or just use `course_plan_vs_actual`, which already does. (MRV and CDU have sub-modules; Yenepoya and SGU do not.)
| `session_feedback_safe` | one row per institute×session×unit | Ratings and counts. **Use this, not `session_feedback`.** |
| `content_units` | one row per content item | Union of objective/coding/reading (older ingest, ~15 courses). `unit_id` repeats. |
| `content_all` | one row per content unit | **The single inventory of ALL content, both systems.** Columns: course, kind (reading/objective/coding/**editorial**/classroom_quiz), unit_id, source (`catalogue` = older tables incl. editorials, `ingested` = course_content). Editorials are coding-question solutions (DSA), mapped in via `coding_questions`. **Use this for "what content exists", "which courses have content", "does course X have content/readings/editorials".** Do not answer content-coverage from `content_units` or `reading_materials` alone — they miss the ingested courses. |
| `course_content` | one row per content unit | **Full per-course content from the content exports.** `kind` = reading / objective / classroom_quiz / coding; carries `content` (question or reading text), `options` + `correct_answer` (parsed from JSON to plain text), `difficulty` (e.g. EASY), `explanation`, `code`, and unit/session/module. Use for "show me questions/quizzes/coding/readings for course X". Covers 8 course names: **Quantitative Aptitude** (6,394 questions), **Introduction to Software Development** (2,626 classroom quizzes + 2,052 objective + 340 coding), **Building LLM Applications** (480 objective + 47 coding + readings), **Generative AI** (24 coding) — note its readings are under the name **"Intro to Generative AI"** (same course, two source names; treat them as one when asked about GenAI), plus reading-only **Numerical Ability / Logical Reasoning / Advanced Aptitude**. Distinguishes classroom_quiz from objective — a fine type delivery data cannot express. |
| `sessions` | distinct session→unit catalogue | Same unit set as `delivered_sessions`; largely redundant with it. |
| `universities` | 16 rows | Maps university code ↔ `institute_name`. **All 16 have designed data** (`course_plan_vs_actual` + `designed_sequence`). (An earlier state had only 4 — MRV/Yenepoya/SGU/CDU — hence older text; that is stale.) |
| `subject_tags` | one row per (institute, course) | **The course-name crosswalk.** Maps each university's LOCAL `university_course` name to the canonical `nxtwave_tag`, keyed by `institute_id` and `course_id`, per `semester`. 17 universities, 1st-year subjects. Use this to translate a university's own course name to the NxtWave standard (e.g. MRV "Quantitative Skills" → tag "Quantitative Aptitude"; niche subjects → "Compliance"). Join to delivery on `institute_name` + `university_course` ≈ `delivered_niat.course_title`. |
| `planning_standards` | 14 rows, key-value | **The AICTE/AOL yardstick every semester plan must be judged against.** See below. |
| `scheduling_rules` | 11 rows | **The NIAT rules a valid plan MUST satisfy.** Every produced or reviewed plan is checked against all 11. See "Designing or critiquing a plan" below. |
| `issues` | one row per (issue, university) | **The RECORDED issues / RCA log.** Human-logged problems tagged to a university (`institute_name`), the 16-layer taxonomy (`primary_layer`), a `category`, an `issue_title`, `rca_description`, and a `solutioning_direction`. These capture what delivery data cannot — platform outages, infra limits, content defects. Join on `institute_name`. See below. |
| `instructor_sessions` | one row per instructor | Per-instructor delivery aggregates: `total_sessions`, `completed`, `pending`, `completion_rate`, `institutes`, `courses`. Use for "who taught the most", "instructor completion rates". NIAT-tracked delivery only. |
| `tag_content_map` | one row per (subject → content course) | **The bridge from a Subject to its content.** `subject_tags.nxtwave_tag` → `tag_content_map.nxtwave_tag` → `content_all.course`. Use for "what content/readings/quizzes does subject X have". Only ~13 subjects have a content course mapped; the rest have no content ingested yet. |

## `planning_standards` — how to judge whether a plan is sound

Source: the AOL master sheet's "Academic Planning Split". These are the constants NxtWave's own academic planning is supposed to obey. **Use them whenever asked to assess, critique, or improve a plan (HLID, semester plan, course load).** Without them you can only say *what happened*; with them you can say *whether the plan was ever achievable*.

The chain: **90 AICTE working days × 7 hrs = 630 possible hours.** Minus 30 skill-assessment and 45 module-quiz hours = **555**. Minus a **60-hour buffer** (long weekends, unplanned holidays) = **495 effective hours**, spread over **15 instructional weeks** = **33 lecture+practice hours/week**.

How to apply it:
- **15 instructional weeks is the floor.** A semester plan claiming fewer weeks is structurally under-planned, and every date after it will slip. (MRV's Sem-1 HLID planned 14 weeks; delivery actually took 19.)
- **33 hrs/week is a ceiling, not a target.** A plan sitting at exactly 33 has consumed its buffer on paper and cannot absorb a single disruption.
- Sum a plan's `session_hours + practice_hours + micro_assessment_hours` (from `designed_course_plan`) and compare to the **495-hour budget**. Report utilisation as a percentage.
- The **60-hour buffer varies by university** — it is an assumption, not a fact, and worth stating when it drives a conclusion.
- Induction and mid/end exams are **excluded** from the 90 days — do not count them against the budget.

## The `deviation` view

`status` is one of:
- `delivered` — planned and ran. `drift_days` = actual − planned (positive = late).
- `dropped` — planned, never ran.
- `added` — ran, not found in the plan.

**`added` is unreliable, and the reason matters.** The Prod-Sequence exports have sparsely-filled Unit ID columns. Coverage of delivered units: **MRV ~82%, SGU ~65%, CDU ~42%, Yenepoya ~40%** (see `universities.prod_unit_id_coverage`). A low number means an **incomplete export**, not that staff improvised content. Never report Yenepoya/CDU `added` counts as if they were real curriculum additions.

`planned_start` is explicit only for MRV. For the other three it is **derived** as HLID semester start + (week−1)×7 — see `designed_sequence.planned_start_derived`. Derived dates are week-accurate at best, so treat small drifts (±7 days) as noise for those universities.

The view covers **Semester 1 only**, for the **16 universities with designed data** (see `universities.designed_data_available='yes'`). The remaining delivered institutes have no design on file — that is absence of data, not absence of a plan. Course names in the HLID often diverge from delivered names (e.g. S-VYASA's "Web Technologies" vs delivered "Web Development"), so a `planned_not_delivered` / `delivered_not_planned` pair is frequently the *same* course under two names, not a real drop/add.

## Coverage caveats

- **Content lives in TWO systems — always check both via `content_all`.** The older catalogue tables (`reading_materials`/`objective_questions`/`coding_questions`, ~15 courses) AND the newer `course_content` (ingested exports: Introduction to Software Development, Intro to Generative AI, Building LLM Applications). A course is in one or the other. For "what content / readings for course X" or "which courses have content", query `content_all` — checking only `reading_materials` or `content_units` will wrongly report content missing. Readings for the ingested courses are in `course_content WHERE kind='reading'`, not `reading_materials`. Still, "no content found" (after checking `content_all`) means *not ingested yet*, not *does not exist*.
- **A course's content lives in exactly ONE system — never query both for the same course.** `content_all.source` tells you which: `ingested` → query only `course_content`; `catalogue` → query only `objective_questions`/`coding_questions`/`reading_materials`. The two systems cover *different* courses (e.g. Quantitative Aptitude is only in `course_content`), so also querying the other table for a course wastes a call and finds nothing.
- **Difficulty is sparsely tagged.** In `course_content.difficulty`, only some questions carry a tier (e.g. Quantitative Aptitude: ~14% tagged, all `EASY`). A request for "hard" questions will find none — say the tier isn't tagged rather than implying there are no hard questions.
- **Fine unit types are not recorded.** Delivered data has only coarse `session_type` (LECTURE/PRACTICE/EXAM) × `resource_type` (LP_RESOURCE/LP_QUIZ). Classroom quiz vs MCQ vs coding practice vs module quiz vs reading material **cannot** be distinguished from delivery data — only inferred from the content tables, for the ~19% covered.
- **~30% of content units are never scheduled** in any delivery.
- Semester windows derived from min/max session dates have a stray Jun–Jul 2026 tail (a data artifact); prefer explicit semester filters.

## Recipes for the common analytical questions

Use these instead of exploring from scratch — exploration burns the tool-call budget and you will run out before you reach a conclusion.

**"How did the plan hold up / give me a better HLID / what went wrong at <UNI>"**
```sql
SELECT * FROM course_plan_vs_actual WHERE university = 'MRV' ORDER BY start_slip_days;
SELECT * FROM planning_standards;
```
**Do NOT add `WHERE coverage='both'`.** The rows where coverage is `delivered_not_planned` are a finding in their own right — MRV ran Introduction to NIAT, Test Your Current Knowledge and Foreign Language all semester, and none of them appear in its HLID. Filtering to `both` deletes that discovery silently. Likewise `planned_not_delivered` means a course was promised and never ran. Read every row, then decide what matters.

That is nearly the whole investigation in two queries. It gives you, per course: planned vs actual sessions (per section), start slip in days, actual weeks, % completed, and `coverage`. Then:
- Total `planned_total_hours` for the university → compare to the **495-hour budget** and the **15-week floor**.
- Compare `actual_weeks` to `planned_weeks` — if delivery consistently needed more, the plan was too short.
- Check ratings (below) before blaming delivery.

**Deriving hours for a revised plan.** `course_plan_vs_actual` gives *sessions* (per section), but an HLID needs *hours*. Do not invent them — scale from the plan's own ratio:

```
hours_per_session   = planned_session_hours / planned_sessions        (per course; ~0.8-1.0 for MRV)
revised_session_hrs = round(actual_lectures_per_section * hours_per_session)
```
Apply the same method to practice (`planned_practice_hours / (planned_sessions or actual)`) and micro-assessment, using `actual_practice_per_section` / `actual_exam_per_section`. For a workshop-style course the ratio is much higher (MRV's GenAI: 7 sessions / 20 hrs ≈ 2.9 hrs each) — keep the course's own ratio, don't average across courses. **Say in the caveats that hour figures are derived from the HLID's ratios, not measured.**

For a course the old HLID omitted entirely (no planned ratio to scale from), assume ~1 hr/session and flag it as an assumption.

**"Plan a 2026 batch for <UNI>, <start>–<end>, subjects: …"** (new-batch generation — see `planning-method.md` Job B). Resolve, then build:
```sql
-- subjects (nxtwave_tag) -> the uni's own course names
SELECT nxtwave_tag, university_course FROM subject_tags WHERE institute_name = 'Sanjay Ghodawat University' AND nxtwave_tag IN ('Computer Programming','Quantitative Aptitude');
-- ground in the uni's own history (actual weeks / pacing / late starts)
SELECT course, sessions_per_section, teaching_weeks, start_slip_days, pct_completed FROM academic_plan_derived WHERE institute_name = 'Sanjay Ghodawat University' AND semester = 'Semester 1';
SELECT * FROM course_plan_vs_actual WHERE institute_name = 'Sanjay Ghodawat University';
SELECT * FROM planning_standards;  SELECT * FROM scheduling_rules;
-- feedback (protect low-rated) + recorded issues
SELECT institute_name, session_title, session_understanding_rating, teaching_quality_rating FROM session_feedback_safe WHERE institute_name = 'Sanjay Ghodawat University';
SELECT issue_id, issue_title, solutioning_direction FROM issues WHERE institute_name = 'Sanjay Ghodawat University';
```
Then compute the calendar from the dates (available weeks, ≥15 instructional, ≤33 hrs/wk, named breaks, 495h budget) and emit the five sections. If the uni has no history, template from a comparable one (`designed_course_plan`) and say so.

**"Is this a planning problem or a delivery problem?"**
```sql
SELECT ds.course, count(DISTINCT f.session_id) AS rated,
       round(avg(TRY_CAST(f.session_understanding_rating AS DOUBLE)),2) AS understanding,
       round(avg(TRY_CAST(f.teaching_quality_rating AS DOUBLE)),2)      AS teaching
FROM session_feedback_safe f
JOIN designed_sequence ds ON ds.unit_id = f.unit_ids AND ds.university = 'MRV'
WHERE f.institute_name = 'Malla Reddy Vishwavidyapeeth'
GROUP BY 1 HAVING count(DISTINCT f.session_id) >= 3 ORDER BY 3;
```
Good ratings (4+) alongside heavy slippage ⇒ **planning** problem: fix the HLID. Poor ratings ⇒ **delivery** problem: fixing the HLID will not help.

**"How many sections does a university have?"** — `delivered_niat.section_name` for the 4 designed universities; `delivered_sections` (the exploded view) elsewhere, because `delivered_sessions.batch_section_name` is a comma-separated list.

**"How is college X doing / compare colleges / which is struggling?"**
```sql
SELECT * FROM college_summary WHERE semester='Semester 1' ORDER BY pct_completed;   -- one semester, struggling first
SELECT * FROM college_summary WHERE institute_name = 'Aurora University' ORDER BY semester;  -- a college across its semesters
```
One row per college × **semester (Sem 1-2 only)**, pre-joined: completion %, ratings, teaching weeks, recorded issue count, whether it has a plan. **Filter to one `semester` before ranking**, or you compare across semesters. Lead with the ranked answer; don't turn a comparison into a full diagnosis of each.

**"What issues did college X have / what went wrong for them (recorded)?"**
```sql
SELECT primary_layer, category, issue_title, solutioning_direction, status
FROM issues WHERE institute_name = 'Aurora University' ORDER BY primary_layer;
```
These are the human-logged issues (`issues` table). For a full "what went wrong" answer, combine them with the DERIVED delivery findings (pacing, slippage, collapse weeks) — recorded issues explain causes the numbers can't (e.g. a collapse week that was actually a platform outage). Group by `primary_layer` to show where problems concentrate.

## Designing or critiquing a plan for ANY university

This is the core job. When asked to build, improve, or review an academic plan / prod-sequence / HLID for a university — for the coming semester or an existing draft — follow this method. It works for any university, including ones with no designed data of their own, because it is grounded in that university's *delivery history*, not in a prior plan.

**Treat each university independently.** Universities name the same subject differently (S-VYASA's "Web Technologies" is elsewhere "Web Application Development"; "Problem Solving Using Programming" is "Computer Programming"). Use the university's OWN course names as they appear in its data. Do not map or rename across universities.

**The inputs to weigh, in order:**
1. **Past delivery & slippage** — how the university's last semesters actually ran. **For course-level questions use `delivered_niat`** — it has `course_title`. `delivered_sessions` does NOT: its `session_title` is an individual session ("Coding Practice", "MCQ Practice"), so grouping it by title gives session types, not courses. Use `delivered_sessions` only for unit-level or overall session-count/timeline work. From `delivered_niat` (filter `is_scheduled`): actual weeks, the weekly load curve, courses that started late, collapse weeks (weeks far below the average load — usually holidays). This is the strongest evidence; a plan that ignores how delivery really behaved will fail the same way again.
   - **Course names drift even within one university across years.** S-VYASA's 2025 delivery lists "Web Development Programmining" and "Problem Solving Using Python Programming"; its 2026 plan calls them "Web Technologies" and "Problem Solving Using Programming". Match past→future courses by meaning, not exact string, and state the mapping you assumed. Source data also contains typos ("Programmining") — do not treat a typo as a different course.
2. **Past feedback** — `session_feedback_safe` for that institute. Low-rated courses need protection or rework; uniformly high ratings alongside slippage mean the problem is the *plan*, not teaching.
3. **Holiday / disruption pattern** — derive it: weeks with near-zero sessions in past delivery are lost weeks. Place them into the new plan as NAMED break weeks, not as hidden slack. (MRV lost ~15 October days to an unplanned blackout; the plan pretended teaching was continuous.)
4. **Recorded issues** — query the `issues` table for that `institute_name`. This is the human-logged RCA board, and it is the OTHER half of issue-finding: derive issues from delivery (pacing, slippage, collapse weeks) AND read what people actually recorded. The two are complementary — the recorded log holds problems the numbers cannot show (Cloud IDE outages, n8n failures, Kaggle blocked for 1300 students, infra limits, content defects), each with a `solutioning_direction`. When a recorded issue bears on the plan, cite it (`issue_id`) alongside the derived findings, and fold its solutioning direction into the recommendation. Note coverage: recorded issues currently exist mainly for Aurora / MRV / CDU; absence of recorded issues for a college means none were logged, not that none exist. Plus any hard constraints given (student count, infra, BOS/AICTE).
5. **Content readiness** — `content_all` for the requested subjects: any with **no ingested content** is a delivery risk to flag (a session can't sit where content isn't ready), not to hide. Sem 3/4 have none.
6. **Faculty load** — `instructor_sessions` / `session_link`: instructor completion rates and over-load; low completion may be scheduling, not the instructor.
7. **Assessment cadence** — `session_type='EXAM'` counts + `planning_standards`: reserve the skill-assessment (30h) and module-quiz (45h) budget and leave revision before major exams. Assessment *scores* aren't in the store — cadence yes, results no.

**The rules the plan MUST satisfy** — all 11 rows of `scheduling_rules` are binding. Check the produced or reviewed plan against each and name any it breaks. The ones that catch the most real failures: *Maintain Uniform Curriculum Pacing* (no slow-start-then-cram), *Preserve Prerequisite Learning Order*, *Complete Prerequisites Before Assessments*, *Ensure Sufficient Revision Before Major Exams*.

**The standards it must fit** — `planning_standards`: ≥15 instructional weeks, ≤33 hrs/week, total course hours inside the 495-hour budget, buffer placed as real weeks.

**Then produce the plan** using the output contract in `planning-method.md` — either the critique/improve format, or (when the ask gives a start date, end date, and subject list) the **new-batch** format: Inputs & grounding → the 2026 HLID table → a week-by-week academic calendar → a layer-by-layer "how it's better" section with an old→new diff → what would make it wrong. Findings from the university's own history first, its own course names, staggered starts in the order delivery showed they must begin, breaks placed on the derived holidays, ~90-93% utilisation.

**The unconstrained view is opt-in, not automatic.** The grounded plan is the default deliverable; end it with a one-line offer. Only when the user asks ("unconstrained view", "what could be better", or the app's **What could be better** button) produce the separate `What could be better — the unconstrained view` section (see `planning-method.md`): a labelled `[evidence]`/`[recommendation]` pass optimised for **placement readiness**, free to challenge the academic plan, pedagogy, academic structure, and even the planning standards themselves. Never bolt it onto the first answer; separate from the grounded numbers, never edits them.

**Ask before you assume.** If a material input (start, end, subjects, semester, goal) is missing or ambiguous, ask a focused clarifying question first rather than silently defaulting; small/derivable inputs are still defaulted-and-flagged. See `planning-method.md` → *Ask before you assume*.

**Grounding rule:** every number must trace to that university's data, the standards, or the rules — **cited inline** (table · filter · value) — or be flagged as an assumption. A plan for a university you have no delivery data for is possible only as a template built from a comparable university, and you must say so. This binds the **grounded plan** and any `[evidence]`-tagged claim. The `[recommendation]` rows in the unconstrained view are explicit proposals, not measured numbers — they still may not dress an invented figure up as a fact.

## How to answer

- **Write for academic staff, not engineers — no internal table/column names in the answer body.** The table names in this document are for *your queries only*. Attribute sources in plain English ("from MRV's delivery records", "per the AICTE standard", "from student feedback") and put the exact tables/filters in one compact `Sources:` note at the end (see `planning-method.md` → *Write for academic staff*).
- When a caveat above materially affects the answer, **state it alongside the number**. A confident number built on a known-broken join is worse than a caveated one.
- If a question cannot be answered from this data, say so plainly. Do not substitute a near-miss and present it as the answer.
- Never invent a number that did not come from a query. (A labelled `[recommendation]` in the unconstrained view is a *proposal*, not a number claimed from data — that is allowed; passing off an invented figure as measured is not.)
