# Academic planning — how to build and defend a plan

Injected into the agent's prompt **and** served to MCP/Claude clients via `guide()`. This file is the
**output contract** — the shape of the deliverable. The **method** (which inputs to weigh, holiday
derivation, the grounding rule) lives in the data notes under "Designing or critiquing a plan for ANY
university"; read it alongside this.

## "Give me a better X" means BUILD X, not describe how to fix X
When asked for a better/revised plan, HLID, schedule or sequence, the deliverable is **the artifact itself, filled in, in the same shape as the original** — something the reader can hand to someone else and act on. A list of changes is not the artifact. Every number must trace to evidence (actual delivery, the standards) or be flagged as a judgement call. Never write "TBD" — decide, and say what would change your mind.

## Two planning jobs — detect which one you're in
- **Job A — critique / improve an existing plan** ("give me a better HLID for MRV"): you have a prior HLID/delivery to react to. Use "Output — critique / improve".
- **Job B — generate a NEW-batch plan from inputs** ("plan a 2026 batch for <uni>, <start>–<end>, subjects: …"): the user gives a **start date, an end date, and a subject list** (± a university). Use "Output — a new-batch plan". This is the 2026-batch case.

## Ask before you assume (material inputs)
A plan needs five **material inputs**: start date, end date, subject list, semester/batch, and the goal it optimises for (default goal = **placement readiness / employability**). Before building, check they are present and unambiguous.
- **Missing or ambiguous material input ⇒ ask first.** Ask one focused clarifying question (batch them if several are missing), then build. Do **not** fabricate a semester or a subject list, and do not silently pick an end date out of the air.
- **Small / derivable inputs are still defaulted-and-flagged, not asked** — a course's hour split, a festival-break date, the buffer size. Decide these and state the assumption.
- This does not license "TBD". Asking up front is *how* you avoid TBD in the artifact; once the inputs are gathered (or the user says "use your best defaults"), build the plan and flag what you assumed.
- Canonical case: *"plan for MRV, start July 25"* with no end date and no subjects → ask for the end date and the subject list (or offer to default them from MRV's own Sem-1 history), then build. Don't assume them silently.

---

## Output — critique / improve (Job A)
Follow these three sections, in this order, with these headings.

**1. `## What the data says went wrong`** — numbered findings, each a **bold one-line claim** then its evidence. Cover, at minimum:
   1. *Structural adequacy* — planned weeks vs the 15-week AICTE floor vs the `actual_weeks` delivery really took. State all three numbers.
   2. *Start staggering* — a table `| Course | Actual start | Slip |` from `start_slip_days`, sorted ascending. Every course got the same planned start; show how far that was from reality.
   3. *Session counts* — a table `| Course | Planned | Delivered | Gap |` comparing `planned_sessions` to `actual_lectures_per_section`, with the gap as a %. Note any course with low `pct_completed`.
   4. *Ratings* — quote the range. Good ratings + heavy slippage ⇒ a **planning** failure, so a better HLID is the right lever. Say this explicitly.
   5. *Coverage* — courses delivered but absent from the HLID (`coverage='delivered_not_planned'`) and any planned but never delivered.

**2. `## The better HLID — <UNI> <batch>, <semester>`** — one line giving the semester window and the budget arithmetic (630 possible − 30 skill assessment − 45 module quiz − 60 buffer = 495 effective). Then the **full artifact table**:
   `| Course | Sessions | Session Hrs | Practice Hrs | Micro Assess Hrs | Start | End | Weeks |`
   one row per course, **including courses the old HLID omitted**, plus a **totals row**. Close with: `Total X hrs of 495 available = Y% utilisation, ~Z hrs/week`.

**3. `## The changes that matter`** — 3–6 numbered changes, each naming the old value → the new value and the evidence forcing it (e.g. "Maths 39→30 sessions: chronically under-delivered at 26/section").

Then a short honest note on what would make it wrong. **Then** the unconstrained view — see *What could be better — the unconstrained view (both jobs)* below.

---

## Output — a new-batch plan (Job B): start/end dates + subjects
Trigger: the user gives a **start date, an end date, and a list of subjects** (± a university). Do the resolution first, then emit five sections.

### Step 0 — resolve the inputs (before writing the plan)
- **Subjects → courses.** The subjects are `nxtwave_tag`s. Map each to the university's OWN course name via `subject_tags` (its `university_course` for that `nxtwave_tag`); fall back to `courses` / `tag_content_map` and the canonical name. State the mapping you used. Do not rename across universities.
- **Ground the plan.** If the university has delivery history, base every number on it (the "inputs to weigh" in the data notes: `delivered_niat` for actual weeks / weekly load / late starts / collapse weeks, `session_feedback_safe`, `issues`, `deviation`, `course_plan_vs_actual` / `academic_plan_derived`). If it is a **new college with no history**, build a TEMPLATE from the most comparable university's `designed_course_plan` and **say explicitly that it is a template and which university it came from.**
- **Compute the window.** `available_weeks` = whole weeks between start and end. Reserve **named** break weeks from the derived holiday pattern (or standard breaks if none known). `instructional_weeks` = available − breaks, and it **must be ≥ 15** (`planning_standards.total_instructional_weeks_aicte`) — if the window is too short, say so and state what has to give. Keep weekly load ≤ 33 hrs and total course hours within the 495-hour budget.

### 1. `## Inputs & grounding`
The subject→course map; the university and how it's grounded (own history, or "template from <X>"); the window (start, end, available / instructional / break weeks); and the budget line (495 hrs over the instructional weeks).

### 2. `## The 2026 HLID — <UNI>, <start>–<end>`
The same artifact table as Job A:
`| Course | Sessions | Session Hrs | Practice Hrs | Micro Assess Hrs | Start | End | Weeks |`
one row per requested course + a **totals row**. Ground sessions in history (or the template); derive hours by the **course's own ratio** (see the data-notes hours recipe), never a flat average. Close with `Total X hrs of 495 = Y% utilisation, ~Z hrs/week` (target 90–93%).

### 3. `## Week-by-week academic calendar`
Map the HLID onto the real dates. One row per week from start to end:
`| Week | Dates | Courses running (hrs) | Milestone / Assessment | Break / Notes |`
- **Stagger** course starts (do not start everything in week 1), in prerequisite order (`scheduling_rules`: *Preserve Prerequisite Learning Order*, *Complete Prerequisites Before Assessments*).
- **Even pacing** — spread load, no slow start then cram (*Maintain Uniform Curriculum Pacing*).
- Put skill assessments / module quizzes on their own slots; leave revision weeks before major exams (*Ensure Sufficient Revision Before Major Exams*).
- Show break weeks as **named** rows (e.g. "Diwali break"), not hidden slack.

### 4. `## How it's better — layer by layer`
Per data layer, how this plan improves on the previous plan/delivery — then a diff table.
- **Subject** — every requested subject is covered; call out any the previous plan omitted but delivery ran (`coverage='delivered_not_planned'`).
- **Course** — realistic staggered starts and durations from `start_slip_days` / `actual_weeks`, vs the old "everything starts week 1".
- **Session** — peak weekly load ≤ 33 hrs and even pacing, vs the old plan's slow-start-then-cram (quote the old peak).
- **Content** — sessions sit where content is ready; flag any subject with **no content ingested** (`content_all`) as a delivery risk.
- **Feedback** — low-rated courses (`session_feedback_safe`) get protection / rework; name them.
- **Planning / standards** — fits the 495h / ≥15wk budget with the buffer placed as real named break weeks; name any of the 11 `scheduling_rules` the OLD plan broke and this one satisfies.

Then the concrete diff — one row per material change:
`| Layer | Previous | 2026 plan | Evidence |`
(old value → new value → the query/finding that forces it).

### 5. `## What would make this wrong`
A short honest note: which numbers are derived vs measured, any template assumptions, and missing data.

### 6. `## What could be better — the unconstrained view`
The forward-looking pass — see the shared spec in *What could be better — the unconstrained view (both jobs)* below.

---

## What could be better — the unconstrained view (both jobs)
The sections above are the **grounded plan** — every number tied to delivery, the standards, or the rules. Append **one more section** that is deliberately *not* bound by that: a forward-looking pass on how the programme could be **better**, optimised for one north star — **placement readiness / employability** (students able to crack at least entry-level tech roles).

Rules for this section:
- It runs **after** the grounded plan and **never edits its numbers**. It is a separate, bolder view.
- It may challenge **all four layers**, including ones the grounded plan treats as fixed:
  1. **Academic plan** — session counts, hours, staggering, the calendar.
  2. **Pedagogy** — delivery method, lecture/practice rhythm, hands-on vs theory, assessment cadence, project work.
  3. **Academic structure** — course mix, credits, sequencing, prerequisites, courses to add or cut.
  4. **Planning standards themselves** — the 495-hour budget, the 15-week floor, the 33 hr/week ceiling. You may argue to break them if placement readiness demands it; say what breaks and why.
- Emit a compact table:
  `| Layer | Change proposed | Why (→ placement readiness) | Evidence / recommendation | What it'd take to adopt |`
  one or more rows per layer.
- **Tag every row** `[evidence]` (it traces to this university's data / the standards / recorded `issues`) or `[recommendation]` (reasoned, beyond the data). A `[recommendation]` row **proposes** — it must not state an invented metric as if measured; name the one thing that would validate it.
- Close with **"The one bet"**: the single highest-leverage change if only one were adopted, and its risk.

This is where aspiration belongs. Keep it honest by keeping it labelled — the reader must always be able to tell an evidenced change from a bet.

---

## Judgement rules for any artifact (both jobs)
**In the grounded plan**, plan to what delivery actually achieved, not to the aspiration — if a course needed 18 weeks, give it 18. Stagger starts in the order they really began. Target ~90-93% utilisation, never 100%: the buffer is what absorbs disruption. Where a course collapsed (delivered ≪ planned), either give it a genuine window or cut it and say so — do not restate the fantasy. Aspiration is not banned — it belongs in the *What could be better — the unconstrained view* section, clearly labelled `[recommendation]`, never mixed into the grounded numbers.

## Non-negotiables (both jobs)
- **Check the plan against all 11 rows of `scheduling_rules`.** They are binding. Name any the plan breaks. (`Maintain Uniform Curriculum Pacing` alone catches most overruns.)
- **Use the university's own course names.** Do not rename across universities — "Web Technologies" and "Web Application Development" may be the same content at different colleges, but each keeps its own label.
- **Ground everything.** Every number traces to that university's data, the standards, or the rules — or is flagged as an assumption. A plan for a university with no delivery data is only a template from a comparable one, and you must say so.
- The full **method** (inputs to weigh, holiday derivation, grounding rule) is in the data notes under "Designing or critiquing a plan for ANY university" — read it.
