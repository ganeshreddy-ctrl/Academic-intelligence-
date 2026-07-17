# AIP Chat Agent (Streamlit) — Design Doc

**Date:** 2026-07-17
**Status:** Draft for review
**Owner:** Gen-AI Content team, NxtWave
**Implements:** §4.4 (Chat agent) and §6 (Learning loop) of [Academic Intelligence Platform design](2026-07-10-academic-intelligence-platform-design.md)

---

## 1. Problem & Goal

The canonical store now holds content, sessions, feedback, the course catalogue, and (after this work) delivered scheduling and the designed HLID/Prod sequence. Answering questions against it currently requires someone who can write SQL and knows the join-key quirks.

**Goal:** a ChatGPT-style Streamlit app where the team asks **any question the data can answer**, in plain English, and gets a grounded answer that shows its reasoning.

This is a **general-purpose Q&A agent over the whole store**, not a deviation tool. Deviation is one of many things it should handle. The agent must be equally able to answer, for example:
- *"How many coding questions exist for Data Structures using C++?"* (content)
- *"Which instructors have the lowest session completion rate?"* (operational)
- *"Which sessions at CDU rated below 3 for teaching quality?"* (feedback)
- *"What courses are in the FullStack stack and what are their prerequisites?"* (catalogue)
- *"Which units were delivered late at MRV vs the plan?"* (deviation)
- *"What should we change in Sem 1 next year?"* (advisory)

The design must not privilege any one question shape. Coverage of the **schema** is what determines capability.

**Non-goals (v1):**
- **Self-improvement, and feedback capture itself.** Cut by decision during build. v1 is purely ask-a-question-get-an-answer. Deferred to v2 (§13).
- Model fine-tuning, ever. If the loop returns it will be prompt-context, not training.
- Writing to any source system. The agent is strictly read-only.
- Quoting student free-text feedback (see §7).
- Replacing the fortnightly report or the recommendation queue.

## 2. Scope decisions (confirmed)

| Decision | Choice |
|---|---|
| Question types | All: analytics/metrics, content lookup, and open-ended advisory |
| How it answers | Tool-calling agent with a read-only SQL tool (not single-shot text-to-SQL, not a fixed metrics library) |
| Data scope | Everything: existing canonical + **new** delivered scheduling + **new** designed HLID/Prod sequence |
| Improvement loop | **None in v1.** No feedback capture, no learning. Deferred entirely (§13). |
| Semester scope | Load delivered Sem 1 **and** Sem 2; designed data is Sem 1 only, so the agent says so when asked to compare Sem 2 |
| Hosting | Streamlit Community Cloud |
| Student comment text | **Not exposed to the agent** (ratings + counts only) |

## 3. Architecture

```
Streamlit chat UI (app.py)
      │ question + history
      ▼
Agent loop (aip/agent.py) ──► OpenRouter /chat/completions (tool-calling)
      │  system prompt = live schema + data notes   (static)
      │  tool: run_sql(query)
      ▼
DuckDB read-only (aip/db.py) — aip.duckdb rebuilt at startup from committed data
      │  content_* · sessions · session_feedback_safe · courses · course_crosswalk
      │  + delivered_sessions + delivered_niat + designed_sequence
      │  + designed_course_plan + deviation view
      ▼
answer → UI renders it. That is the whole loop.
```

**Nothing persists.** No feedback store, no Sheet, no service account. The app is stateless beyond the browser session. That is what makes v1 deployable with two secrets and nothing else.

**Why a tool-calling agent:** one mechanism covers all three question types — analytics are aggregations, content lookup is a select, advisory is query-then-reason. It can iterate (query → look → refine), which single-shot text-to-SQL cannot.

**Accountability without a UI affordance:** the agent is required to explain its own reasoning in the answer — what it queried, what it filtered, what the number counts, and any caveat that changes how it reads (§5). That is the only audit surface in v1, since the SQL trace is no longer shown.

## 4. Data layer

### 4.1 New committed tables

| Artifact | Built by | Contents |
|---|---|---|
| `data/canonical/delivered_sessions.parquet` | `scripts/build_delivered.py` | institute_name, batch_section_name, semester, session_id, session_title, session_type, resource_type, unit_id, start_ts, end_ts |
| `data/canonical/delivered_niat.parquet` | `scripts/build_delivered.py` | institute_name, batch_name, section_name, semester, course_title, session_title, session_type, session_status, instructor_name, instructor_category, week_count, start_ts, end_ts, is_scheduled |
| `data/canonical/designed_sequence.csv` | `scripts/build_designed.py` | university, course, topic, unit_id, week, planned_start, session_name, type, seq |
| `data/canonical/designed_course_plan.csv` | `scripts/build_designed.py` | university, course, sessions_count, session_hours, practice_hours, micro_assessment_hours, start_timeline, end_timeline, weeks_required |

**Parquet for `delivered_sessions`:** ~396K rows would be a ~50 MB CSV; Parquet compresses to a few MB, carries types (no Excel-serial re-parsing), and DuckDB reads it natively. Matters on a 1 GB Streamlit Cloud box. The other two tables are small — CSV, consistent with the existing canonical layout.

**Excel serials are converted at build time** (epoch 1899-12-30) so `start_ts`/`end_ts`/`planned_start` are real timestamps. The agent must never see a raw serial.

### 4.2 Extensions to `scripts/load_duckdb.py`

- Load the four new artifacts (+ `universities.csv`).
- Keep the existing `content_units` view.
- `session_feedback_safe` view — `session_feedback` **minus** the `positive_feedbacks` / `neutral_feedbacks` / `negative_feedbacks` comment-text columns; exposes ratings and `total_feedbacks` only. The agent is pointed at this view, never the base table (§7).
- `deviation` view — a **convenience view**, one of several. It encodes the designed↔delivered join (on `unit_id`, per university) so the agent need not reinvent the trickiest join in the store. Columns: university, course, unit_id, planned_start, actual_start, drift_days, status (`delivered` / `dropped` / `added`).

Views exist to pre-solve joins the agent would otherwise get wrong. `deviation` is the first because it is the hardest — not because deviation questions matter more than others. Add further views only when a real question proves a join is being fumbled repeatedly.

### 4.3 Schema knowledge (the asset that makes "any question" work)

Two parts, injected into the system prompt:
1. **Live schema** — `aip.db.schema_text()` introspects the database at runtime (every table/view, columns, types, row counts).
2. **`docs/data-notes.md`** — hand-written semantics the schema cannot express: the join-key contract, each table's grain, and the coverage caveats (§4.4).

This is the highest-leverage part of the design. A general-purpose agent is only as capable as its schema knowledge: without being told that `unit_id` is the universal key, that `session_id` is stored dash-less, that `course_crosswalk` is required to bridge course titles, or that `session_type` is coarse, the agent will silently write plausible wrong SQL. Schema coverage — not clever prompting — is what determines how many questions it can answer.

**Implementation note:** an earlier draft specified a *generated* `data-dictionary.md`. Live introspection replaces it: same content, no generation step, and it is structurally incapable of drifting from the database. Only the hand-written semantics need maintaining.

### 4.4 Known data caveats the agent must be told

These go into the system prompt verbatim, because they change how answers should be read.

**Join-key contract (applies to every question):**
- `unit_id` is the universal key across content, delivered, designed, and feedback. It is the spine — prefer it.
- `session_id` is stored **dash-less** (32-hex) in `sessions` and `delivered_sessions`. Feedback is normalized to match; never join on a dashed UUID.
- Course titles do **not** join directly. `course_crosswalk` is required to bridge delivered ↔ catalogue ↔ content; only ~50% of delivered session volume maps, the rest are `unmapped`. Course counts taken without the crosswalk will be wrong.
- There is **no Subject entity**; `stack` in `courses` is the closest roll-up.

**Coverage / quality caveats (state these when they affect an answer):**
- Content exists for only ~15 course titles of 63 in the catalogue, and reaches ~19% of delivered units. "No content found" usually means *not ingested*, not *doesn't exist*.
- Fine unit types (classroom quiz / mcq / coding practice / module quiz / reading) are **not** a field — delivered data has only coarse LECTURE/PRACTICE/EXAM × LP_RESOURCE/LP_QUIZ. Finer types are only inferable from the content tables, for the ~19% covered.
- ~30% of content units are never scheduled in any delivery.
- Prod-Sequence `unit_id` coverage varies by university (MRV ~82%, SGU ~65%, Yenepoya/CDU ~40%). Low coverage means an **incomplete design export**, not curriculum improvisation — so `status='added'` is unreliable for Yenepoya/CDU.
- Planned dates exist only for MRV; others are derived from `Week` + HLID semester start. MRV's Prod Sequence also mixes an original and a "NEW BATCH" re-plan.

**Behavioural rule:** when a caveat materially affects an answer, the agent states it alongside the number. A confident number built on a known-broken join is worse than a caveated one.

## 5. Agent layer

**`aip/db.py`** — read-only DuckDB connection.
- `run_sql(query) -> rows` guardrails: **SELECT/WITH only** (reject DDL/DML by statement parse, not regex-only), row cap (1,000), statement timeout (10s), result truncation note when capped.
- Guardrails are a trust boundary: the tool argument is model-generated text. This is not a place to be lazy.

**`aip/agent.py`** — OpenRouter tool-calling loop.
- `answer(question, history) -> (text, sql_trace)`.
- Model is a config value (`MODEL` secret), not hardcoded — per the parent design doc's per-agent model config.
- Max 5 tool iterations, then answer with what it has or say it couldn't.
- System prompt = **`docs/data-dictionary.md` (§4.3)** + §4.4 caveats. **Static in v1** — no learned content.
- The prompt is deliberately schema-heavy and instruction-light: breadth of question coverage comes from the agent knowing the data, not from task-specific prompting.

There is no third module. `db.py` + `agent.py` is the whole backend.

## 6. UI

**`app.py`** — `st.chat_message` / `st.chat_input`. That is nearly all of it.

- Chat history for the session (`st.session_state`), a **Clear chat** button.
- Sidebar: the model in use, and a table/row-count list so users can see what the agent can reach.
- Assistant responses render as markdown. Nothing else — no SQL expander, no rating widget.

Cut during build, by decision: the "Show SQL" expander, the 👍/👎 buttons, and the "What could be improved?" box. The trade-off is explicit — **a user cannot inspect the query behind a number, and we capture no signal about answer quality**. The only mitigations are the agent's required self-explanation (§5) and reading Cloud logs. If answer quality becomes a question people are asking, this is the first thing to reinstate (§13).

## 7. Security & data handling

- **Student comment text is never exposed to the agent.** It queries `session_feedback_safe` (ratings + counts). Reason: the app deploys from a GitHub repo to third-party infra; free-text student complaints are the most sensitive thing in the store and add little to the analytics/advisory questions this app serves.
- **OpenRouter key** lives in `st.secrets` (Streamlit Cloud Secrets in prod, gitignored `.streamlit/secrets.toml` locally). Never client-side, never committed.
- **Repo must be private** and the Streamlit app's viewers restricted to org emails.
- **Pre-existing exposure (action required, outside this design):** `data/canonical/session_feedback.csv` already contains comment text and is already pushed to GitHub. If the repo is public, that text is already exposed, and `session_feedback_safe` does not undo git history. Verify repo visibility; making it private is step one. Purging history is a separate task.

## 8. Error handling

| Failure | Behaviour |
|---|---|
| SQL error | Feed the error back to the model for **one** repair retry; if it still fails, surface the failed SQL and say it couldn't answer. Never guess a number. |
| Non-SELECT generated | Guardrail rejects; the model is told why and may retry once. |
| Empty result | Answer "no rows matched" and show the SQL. Never fabricate rows. |
| OpenRouter error/timeout | Retry with backoff; then an honest error message. |
| Tool-iteration cap hit | Answer with what was gathered, stating it was truncated. |

The through-line: **degrade to "I couldn't answer," never to a confident wrong number.**

## 9. Testing

- `tests/test_db.py` — the guardrail is a security path, so it gets real coverage: rejects `INSERT`/`UPDATE`/`DROP`/`ATTACH`/multi-statement; enforces the row cap; a known-count query is stable (MRV Semester 1 = 7,702 delivered session rows).
- `tests/test_build.py` — Excel-serial → timestamp conversion (a known serial maps to a known date); `deviation` view returns the expected MRV overlap (1,174 units).
- `tests/test_agent.py` — a golden set with the OpenRouter call mocked, asserting tool-call shape and that answers cite SQL.

**The golden set must span the breadth of the store, not one question shape.** At least two questions per area: content, catalogue, sessions/delivery, feedback/ratings, instructors, course-crosswalk, designed-vs-delivered, and one open-ended advisory. This set is the regression suite for capability — if a whole area has no golden question, that area's coverage is unverified. Live-model accuracy is judged by the feedback loop, not unit tests.

## 10. Deliberate simplifications (YAGNI)

- **No feedback capture and no auto-learning.** Cut during build. Nothing is stored; the app is stateless beyond the browser session. This also removes the Google Sheet, the service account, and two dependencies.
- No vector search / embeddings — nothing is retrieved in v1, and when the loop returns, notes will be small enough to inject wholesale.
- No auth in the app itself — Streamlit Cloud viewer restriction is the access control.
- No multi-user session state or conversation persistence — chat history lives in `st.session_state` for the session only.
- No agent-written charts in v1 — text answers + tables. Add plots once the questions being asked are known.
- No Postgres — DuckDB rebuilt at startup, per the parent design doc's upgrade path.

## 11. Phasing

1. **Data**: `build_delivered.py`, `build_designed.py`, `load_duckdb.py` extensions + views, and `docs/data-notes.md`. *Done when:* every table's grain and join keys are described in the notes, and the `deviation` view returns **MRV: 989 delivered / 89 dropped / 452 added** from 1,078 designed units.

> **Why not the 1,174 / 154 quoted earlier:** that came from a raw scan of *every* UUID appearing anywhere in the Prod workbook, including reference and scratch tabs (Gamma, Tech courses, rough). The shipped extraction only reads sheets that are actually schedules — a unit-id column plus a week/day/start column — which is narrower (1,078 designed units) and more defensible. The earlier figure over-counted the plan.
2. **Agent core**: `db.py` guardrails + `agent.py` loop, driven from a CLI. *Done when:* the golden set — spanning **all** areas of the store, not just deviation — answers correctly with valid SQL.
3. **UI**: `app.py` chat. *Done when:* the app boots on a machine with no `aip.duckdb`, rebuilds it from committed data, and answers a question end-to-end.
4. **Deploy**: private repo, Streamlit Cloud, secrets, viewer allowlist.

## 12. Open questions

1. **Which OpenRouter model** for the agent? Needs tool-calling + decent SQL. To be picked by running the golden set against 2–3 candidates on accuracy vs cost.
2. **Repo visibility** — confirmed **public** on 2026-07-17, and deployed that way by decision. Student comment text in `session_feedback.csv` is world-readable; the agent cannot read it, but the file is in the repo. Owner: whoever holds student-data policy.
3. **How will we know if answers are wrong?** v1 captures no feedback and shows no SQL. Currently the only answer is "a user notices and says so".

## 13. Deferred to v2 — the learning loop

Cut from v1 by decision, not oversight — including the capture step, so **no data is accumulating meanwhile**. Rebuilding this later starts from zero signal; that is the accepted cost.

When it returns, the likely shape is the one from the parent design doc §6:
- **Correction notes** — human-written facts ("exclude BREAK sessions", "MRV = Malla Reddy Vishwavidyapeeth") injected verbatim into the system prompt. Low risk; probably first.
- **Q→SQL few-shot examples** — promoted from 👍'd answers. Higher risk: a plausible-but-wrong query that earned a 👍 would teach the agent a bad pattern, and this store has real footguns (the course crosswalk, dash-less `session_id`). If added, it needs human curation, not auto-promotion.

**Trigger to build it:** users reporting wrong answers, or nobody trusting the output. Since nothing is logged, that signal arrives by conversation, not by data. Reinstating **capture** (a row per answer: question, SQL, answer) is the cheap first step and unblocks everything else here.
