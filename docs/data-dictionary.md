# Data dictionary

Every table and view in `data/aip.duckdb`, grouped by domain. Tables are the committed
files under `data/canonical/<domain>/`; **views** are built by `scripts/load_duckdb.py`
and pre-solve the cross-domain joins. Query any of them read-only.

**Join keys at a glance:** `unit_id` (universal content key) · `session_id` (scheduling ↔
feedback) · `institute_name` (delivery ↔ feedback ↔ issues) · `nxtwave_tag` (subject ↔
content) · designed↔delivered bridges fuzzily via `session_link` / `course_plan_vs_actual`.

---

## delivery/ — what actually ran

### `delivered_niat` (table · 157,502 rows) — `build_delivered.py`
One row per delivered **session** with course/instructor/status. Grain: institute ×
section × session.
Key cols: `institute_name`, `semester`, `course_title`, `session_title`, `session_type`
(LECTURE/PRACTICE/EXAM), `session_status`, `instructor_name`, `start_ts`, `is_scheduled`.
No `session_id`/`unit_id` — bridged to scheduling via `session_link`.

### `delivered_sessions` (table · 239,372 rows) — `build_delivered.py`
One row per scheduled **unit-session** (the Clickup scheduling export). Grain: session ×
unit.
Key cols: `institute_name`, `semester`, `session_id`, `session_title`, `session_type`,
`unit_id`, `resource_type`, `start_ts`. **`session_id` joins to `session_feedback`;
`unit_id` joins to content.**

### `sessions` (table · 7,086 rows) — `build_operational.py`
Distinct session→unit catalogue (session_id, session_title, session_type, unit_id,
resource_type). A lookup for scheduled sessions.

---

## feedback/ — student ratings

### `session_feedback` (table · 8,529 rows) — `build_operational.py`
One row per rated session. Grain: institute × session_id.
Key cols: `institute_name`, `session_id`, `unit_ids`, `total_feedbacks`,
`session_understanding_rating`, `teaching_quality_rating`, `positive/neutral/negative_feedbacks`.
Joins to scheduling on `session_id`, to content on `unit_ids`.
> Contains counts only — comment text is not stored here. Use the **`session_feedback_safe`**
> view (identical minus any free-text-adjacent columns) for the agent.

---

## instructors/ — delivery by instructor

### `instructor_sessions` (table · 490 rows) — `build_operational.py`
One row per instructor. `instructor_name`, `instructor_category`, `total_sessions`,
`completed`, `pending`, `completion_rate`, `institutes`, `courses`.

---

## planning/ — the designed plan (HLID / Prod Sequence)

### `designed_course_plan` (table · 156 rows) — `build_designed.py`
Course-level plan from each university's HLID "High Level Student Journey". Grain:
university × course. `university` (code), `course`, `sessions_count`, `session_hours`,
`practice_hours`, `micro_assessment_hours`, `start_timeline`, `weeks_required`,
`is_submodule` (WAD-1 component rows, excluded from totals to avoid double-counting).

### `designed_sequence` (table · 12,685 rows) — `build_designed.py`
Unit-level plan (what was meant to run, when). `university`, `course`, `unit_id`, `week`,
`planned_start`, `planned_start_derived`, `seq`. Joins to delivery on `unit_id`.

### `universities` (table · 16 rows) — hand-maintained
Registry mapping HLID `code` → delivered `institute_name`, with
`designed_data_available` and `prod_unit_id_coverage`. **This is the code↔institute join
for all designed-vs-delivered comparisons.**

### `planning_standards` (table · 14 rows) · `scheduling_rules` (table · 11 rows)
Reference constants and rules (e.g. session-hour budgets, scheduling policy) the agent
uses when reasoning about plans.

---

## content/ — learning material

### `course_content` (table · 12,327 rows) — `build_content.py`
Ingested content units (readings, quizzes, coding). Grain: content unit. `course`,
`module`, `topic`, `session_id`, `unit_id`, `kind` (reading/objective/classroom_quiz/coding),
`content`, `options`, `correct_answer`, `code`. JSON is parsed to plain text.

### `reading_materials` · `objective_questions` · `coding_questions` · `editorials` (tables) — `build_canonical.py`
The catalogue-side content, keyed `course_id → topic_name → unit_id`. Readings (543),
objective Qs (19,163), coding Qs (1,039), editorials (141).

### `tag_content_map` (table · 14 rows) — committed reference
Maps a `nxtwave_tag` (subject) → the `content_course` name in the content tables. The
bridge from a **subject** to its **content**.

---

## subjects/ — taxonomy & crosswalk

### `subject_tags` (table · 352 rows) — `build_subject_tags.py` + `_supplement.py`
The crosswalk: a university's local course name → the canonical **NxtWave subject**.
Grain: institute × semester × course. `institute_id`, `institute_name`, `semester`,
`university_course` (local name), `nxtwave_tag` (subject), `course_id`, `credits`.
The base sheet is 1st-year; the **supplement** adds later-semester and delivered-name
variants so delivery links to subjects.

### `subject_tags_supplement` (table) — `build_subject_tags_supplement.py`
Merged into `subject_tags` at load time (then dropped). Maps delivered + HLID course
names to subjects that the base sheet doesn't cover.

### `course_crosswalk` (table · 226 rows) — `build_course_crosswalk.py`
Bridges raw course titles across layers to the catalogue. `layer`, `raw_title`,
`course_key`, `match_status`, `catalogue_course_title`, `stack`.

---

## issues/ — RCA log

### `issues` (table · 119 rows) — `build_issues.py`
Human-logged operational/root-cause issues. `issue_id`, `institute_name`, `primary_layer`,
`category`, `issue_title`, `rca_description`, `solutioning_direction`, `status`. Joins to
delivery on `institute_name`. Coverage: Aurora, Chaitanya (CDU), MRV only.

---

## catalogue

### `courses` (table · 63 rows) — `build_checklist.py` — `data/courses.csv`
The 63-course catalogue across 11 stacks. `stack`, `course_title`, `course_ids`,
`prereq_course_ids`, `ingest_status`.

---

## Views (built by `load_duckdb.py` — the cross-domain joins)

| View | Rows | What it gives you |
|---|---|---|
| **`session_link`** | 157,502 | The spine: every `delivered_niat` session with its `session_id`/`unit_id` where the fuzzy bridge to `delivered_sessions` matched. `linked` + `link_precision` flag confidence (~76% minute, ~85% day). |
| **`academic_plan_derived`** | 335 | Planning metrics derived from *delivery* for **all** universities: sessions/section, teaching_weeks, first/last_session, start_slip_days, pct_completed. |
| **`course_plan_vs_actual`** | 159 | The designed vs delivered comparison per course (16 universities with HLID). `coverage` = both / planned_not_delivered / delivered_not_planned; `session_gap` = actual − planned. |
| **`session_feedback_safe`** | 8,529 | Agent-facing feedback (ratings only, no comment text). |
| **`content_all`** | 33,072 | Unified content across the catalogue tables + `course_content`, keyed by `course` + `unit_id`. Use this for "what content exists". |
| **`content_units`** | 20,745 | Distinct content `unit_id` ↔ `course_title`. |
| **`college_summary`** | 17 | One row per real college: sections, courses, completion, avg ratings, recorded_issues, has_designed_plan. The "how is X doing" table. |
| **`delivered_sections`** | 239,676 | Section-normalised scheduling. |
| **`deviation`** | 24,813 | Unit-level planned_start vs actual_start drift (Sem-1 designed unis). |

---

*The agent's own working notes — join recipes, data caveats, worked query examples —
are in [`data-notes.md`](data-notes.md). This dictionary is the human-facing structural
reference; that file is the "how to query it well" companion.*
