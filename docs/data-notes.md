# Data notes — what the schema cannot tell you

Injected verbatim into the agent's prompt, alongside the live schema. Everything here
is a thing that will produce a confidently wrong answer if ignored.

## Join-key contract

- **`unit_id` is the universal key.** It links content, delivered, designed, and feedback. Prefer it over anything else.
- **`session_id` is stored dash-less** (32-hex) in `sessions`, `delivered_sessions`, and `session_feedback`. Never join on a dashed UUID.
- **Course titles do NOT join across layers.** Delivered has ~148 titles, the catalogue has 63, and the names differ. Use `course_crosswalk` (`raw_title` → `catalogue_course_title`, via normalized `course_key`). Only ~50% of delivered session volume maps; the rest have `match_status='unmapped'`. A course-level count taken without the crosswalk is wrong.
- **There is no Subject entity.** `courses.stack` (11 stacks) is the closest roll-up.
- **`delivered_niat` cannot be joined to `delivered_sessions`.** It carries no `unit_id` and no `session_id`. Use it standalone for instructor / course-title / session-status questions. Do not invent a join on title+timestamp.

## Table meanings and grain

| Table | Grain | Notes |
|---|---|---|
| `delivered_sessions` | one row per session×unit scheduled | What actually ran. `start_ts`/`end_ts` are real timestamps. Sem 1 **and** Sem 2. |
| `delivered_sections` | `delivered_sessions` exploded by section | `batch_section_name` is a **comma-separated list** ("TU Batch-1-S-002, TU Batch-1-S-003"); one row can cover several sections. Use this view for per-section questions — counting `batch_section_name` counts section *groupings*, not sections. |
| `delivered_niat` | one row per planned session | Has course/instructor/status. **34% (53,643 rows) were never scheduled** — `is_scheduled = false`, `start_ts` null. Filter on `is_scheduled` or you will count sessions that never happened. |
| `designed_sequence` | one row per unit per sheet | The plan (HLID/Prod). **Semester 1 only.** May contain the same `unit_id` more than once (MRV has a "NEW BATCH" re-plan alongside the original) — dedupe by `unit_id` when counting. |
| `designed_course_plan` | one row per university×course | HLID "Student Journey": planned session counts, hours, start/end timelines. Sem 1 block only. **`is_submodule='True'` rows are components of the course above them — ALWAYS exclude them from any total** (see below). |
| `deviation` | one row per university×unit | Pre-solved designed↔delivered join. Use this rather than re-deriving it. |
| `course_plan_vs_actual` | one row per university×course | **Pre-solved plan-vs-delivery, already per-section.** Use this for any "how did the plan hold up / give me a better plan" question. |

## ⚠️ `designed_course_plan.is_submodule` — read before summing anything

The HLID lists a course **and then its component modules as sibling rows**. For MRV: `Web Application Development-1` (75 sessions) is followed by `Build Your own Static Website` (28) + `Build Your own Responsive Website` (15) + `Modern Responsive Web Design` (17) + `Build Your Own Dynamic Web Application` (15) — which sum to exactly 75. **They are the same sessions listed twice.**

Summing every row inflates MRV's Sem-1 load from **460 hrs to 593 (+29%)**, turning a sensible 93%-utilised plan into a fictional 120% overload — and every recommendation built on that is wrong. Always filter `WHERE is_submodule <> 'True'`, or just use `course_plan_vs_actual`, which already does. (MRV and CDU have sub-modules; Yenepoya and SGU do not.)
| `session_feedback_safe` | one row per institute×session×unit | Ratings and counts. **Use this, not `session_feedback`.** |
| `content_units` | one row per content item | Union of objective/coding/reading. `unit_id` repeats (many questions per unit). |
| `sessions` | distinct session→unit catalogue | Same unit set as `delivered_sessions`; largely redundant with it. |
| `universities` | 4 rows | Maps university code (MRV/Yenepoya/SGU/CDU) ↔ `institute_name`. Only these 4 have designed data. |
| `planning_standards` | 14 rows, key-value | **The AICTE/AOL yardstick every semester plan must be judged against.** See below. |

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

The view covers **Semester 1 only** and **only the 4 universities with designed data**. There is no design on file for the other 14 institutes — that is absence of data, not absence of a plan.

## Coverage caveats

- **Content covers only ~15 of 63 catalogue course titles, reaching ~19% of delivered units.** "No content found" almost always means *not ingested yet*, not *does not exist*. Say so.
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

## How to answer

- When a caveat above materially affects the answer, **state it alongside the number**. A confident number built on a known-broken join is worse than a caveated one.
- If a question cannot be answered from this data, say so plainly. Do not substitute a near-miss and present it as the answer.
- Never invent a number that did not come from a query.
