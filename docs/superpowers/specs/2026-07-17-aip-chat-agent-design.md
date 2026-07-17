# AIP Chat Agent (Streamlit) — Design Doc

**Date:** 2026-07-17
**Status:** Draft for review
**Owner:** Gen-AI Content team, NxtWave
**Implements:** §4.4 (Chat agent) and §6 (Learning loop) of [Academic Intelligence Platform design](2026-07-10-academic-intelligence-platform-design.md)

---

## 1. Problem & Goal

The canonical store now holds content, sessions, feedback, the course catalogue, and (after this work) delivered scheduling and the designed HLID/Prod sequence. Answering questions against it currently requires someone who can write SQL and knows the join-key quirks.

**Goal:** a ChatGPT-style Streamlit app where the team asks questions in plain English and gets answers grounded in the data — analytics, content lookup, and open-ended advisory — and which improves from per-answer feedback.

**Non-goals (v1):**
- Model fine-tuning. "Learning" is prompt-context (few-shot examples + notes), not training.
- Writing to any source system. The agent is strictly read-only.
- Quoting student free-text feedback (see §7).
- Replacing the fortnightly report or the recommendation queue.

## 2. Scope decisions (confirmed)

| Decision | Choice |
|---|---|
| Question types | All: analytics/metrics, content lookup, and open-ended advisory |
| How it answers | Tool-calling agent with a read-only SQL tool (not single-shot text-to-SQL, not a fixed metrics library) |
| Data scope | Everything: existing canonical + **new** delivered scheduling + **new** designed HLID/Prod sequence |
| Improvement loop | Both: learned question→SQL few-shot examples **and** a durable corrections/notes memory |
| Hosting | Streamlit Community Cloud |
| Student comment text | **Not exposed to the agent** (ratings + counts only) |

## 3. Architecture

```
Streamlit chat UI (app.py)
      │ question + history
      ▼
Agent loop (aip/agent.py) ──► OpenRouter /chat/completions (tool-calling)
      │  system prompt = schema + knowledge_notes + few-shot qa_examples
      │  tool: run_sql(query)
      ▼
DuckDB read-only (aip/db.py) — aip.duckdb rebuilt at startup from committed data
      │  content_* · sessions · session_feedback_safe · courses · course_crosswalk
      │  + delivered_sessions + designed_sequence + designed_course_plan + deviation view
      ▼
answer + SQL trace → UI renders answer, "show SQL", 👍/👎, "What could be improved?"
      │
      ▼
Google Sheet (aip/memory.py): feedback_log | qa_examples | knowledge_notes
      └── read at startup (cached) → injected into next prompt   ← learning loop
```

**Why a tool-calling agent:** one mechanism covers all three question types — analytics are aggregations, content lookup is a select, advisory is query-then-reason. It can iterate (query → look → refine), which single-shot text-to-SQL cannot.

**Why Google Sheets for the loop:** Streamlit Community Cloud has an **ephemeral filesystem** — it wipes on redeploy/sleep, so feedback written to a local file would vanish and the learning loop would silently never accumulate. A Sheet survives restarts, is human-reviewable, and matches how the team already works.

## 4. Data layer

### 4.1 New committed tables

| Artifact | Built by | Contents |
|---|---|---|
| `data/canonical/delivered_sessions.parquet` | `scripts/build_delivered.py` | institute_name, batch_section, semester, session_id, session_title, session_type, resource_type, unit_id, start_ts, end_ts, instructor_name, instructor_category, session_status, course_title |
| `data/canonical/designed_sequence.csv` | `scripts/build_designed.py` | university, course, topic, unit_id, week, planned_start, session_name, type, seq |
| `data/canonical/designed_course_plan.csv` | `scripts/build_designed.py` | university, course, sessions_count, session_hours, practice_hours, micro_assessment_hours, start_timeline, end_timeline, weeks_required |

**Parquet for `delivered_sessions`:** ~396K rows would be a ~50 MB CSV; Parquet compresses to a few MB, carries types (no Excel-serial re-parsing), and DuckDB reads it natively. Matters on a 1 GB Streamlit Cloud box. The other two tables are small — CSV, consistent with the existing canonical layout.

**Excel serials are converted at build time** (epoch 1899-12-30) so `start_ts`/`end_ts`/`planned_start` are real timestamps. The agent must never see a raw serial.

### 4.2 Extensions to `scripts/load_duckdb.py`

- Load the three new artifacts.
- Keep the existing `content_units` view.
- `session_feedback_safe` view — `session_feedback` **minus** the `positive_feedbacks` / `neutral_feedbacks` / `negative_feedbacks` comment-text columns; exposes ratings and `total_feedbacks` only. The agent is pointed at this view, never the base table (§7).
- `deviation` view — encodes the designed↔delivered join **once** (on `unit_id`, per university) so the agent doesn't reinvent it per question. Columns: university, course, unit_id, planned_start, actual_start, drift_days, status (`delivered` / `dropped` / `added`).

Encoding the hard join as a view is the single highest-leverage thing here: it is the join the agent is most likely to get wrong.

### 4.3 Known data caveats the agent must be told

These go into the system prompt verbatim, because they change how answers should be read:
- Prod-Sequence `unit_id` coverage varies by university (MRV ~82%, SGU ~65%, Yenepoya/CDU ~40%). Low coverage means an **incomplete design export**, not curriculum improvisation — `status='added'` is unreliable for Yenepoya/CDU.
- Planned dates exist only for MRV; others are derived from `Week` + HLID semester start.
- MRV's Prod Sequence mixes an original and a "NEW BATCH" re-plan.
- Fine unit types (classroom quiz / mcq / coding practice / module quiz / reading) are **not** a field — delivered data has only coarse LECTURE/PRACTICE/EXAM × LP_RESOURCE/LP_QUIZ.
- ~50% of delivered session volume maps to the catalogue via `course_crosswalk`; the rest are `unmapped`.

## 5. Agent layer

**`aip/db.py`** — read-only DuckDB connection.
- `run_sql(query) -> rows` guardrails: **SELECT/WITH only** (reject DDL/DML by statement parse, not regex-only), row cap (1,000), statement timeout (10s), result truncation note when capped.
- Guardrails are a trust boundary: the tool argument is model-generated text. This is not a place to be lazy.

**`aip/agent.py`** — OpenRouter tool-calling loop.
- `answer(question, history) -> (text, sql_trace)`.
- Model is a config value (`MODEL` secret), not hardcoded — per the parent design doc's per-agent model config.
- Max 5 tool iterations, then answer with what it has or say it couldn't.
- System prompt = schema dump + §4.3 caveats + all `knowledge_notes` + recent K `qa_examples`.

**`aip/memory.py`** — Google Sheets access via service account.
- `load_notes()`, `load_examples()` — cached (`st.cache_data`, TTL 5 min).
- `log_feedback(row)` — append to `feedback_log`.
- `promote_example(question, sql)` / `add_note(text)`.

## 6. UI & the feedback loop

**`app.py`** — `st.chat_message` / `st.chat_input`.

Every assistant response renders, in order:
1. The answer text.
2. A collapsed **"Show SQL"** expander with the query/queries run.
3. **👍 / 👎** buttons.
4. An optional free-text box: **"What could be improved?"**
5. Submit.

Feedback is **per response**, not per session. Each submission appends one `feedback_log` row: timestamp, question, sql, answer, verdict (up/down/none), improvement_text, model.

**How it feeds back:**
- 👍 → the question→SQL pair is promoted to `qa_examples`, injected as few-shot for future questions.
- 👎 and/or improvement text → written to `knowledge_notes` (e.g. *"MRV = Malla Reddy Vishwavidyapeeth"*, *"exclude BREAK sessions"*), injected verbatim into every future system prompt.

No embeddings or vector search in v1 — inject all notes + the most recent K examples. They are small. Add similarity retrieval only when the prompt measurably outgrows the context, not before.

## 7. Security & data handling

- **Student comment text is never exposed to the agent.** It queries `session_feedback_safe` (ratings + counts). Reason: the app deploys from a GitHub repo to third-party infra; free-text student complaints are the most sensitive thing in the store and add little to the analytics/advisory questions this app serves.
- **OpenRouter key** lives in `st.secrets` (Streamlit Cloud Secrets in prod, gitignored `.streamlit/secrets.toml` locally). Never client-side, never committed.
- **Service-account JSON** likewise in secrets.
- **Repo must be private** and the Streamlit app's viewers restricted to org emails.
- **Pre-existing exposure (action required, outside this design):** `data/canonical/session_feedback.csv` already contains comment text and is already pushed to GitHub. If the repo is public, that text is already exposed, and `session_feedback_safe` does not undo git history. Verify repo visibility; making it private is step one. Purging history is a separate task.

## 8. Error handling

| Failure | Behaviour |
|---|---|
| SQL error | Feed the error back to the model for **one** repair retry; if it still fails, surface the failed SQL and say it couldn't answer. Never guess a number. |
| Non-SELECT generated | Guardrail rejects; the model is told why and may retry once. |
| Empty result | Answer "no rows matched" and show the SQL. Never fabricate rows. |
| OpenRouter error/timeout | Retry with backoff; then an honest error message. |
| Sheets unavailable | Chat still answers. Learning degrades gracefully (log to local file, warn in UI). A memory-store outage must not take down Q&A. |
| Tool-iteration cap hit | Answer with what was gathered, stating it was truncated. |

The through-line: **degrade to "I couldn't answer," never to a confident wrong number.**

## 9. Testing

- `tests/test_db.py` — the guardrail is a security path, so it gets real coverage: rejects `INSERT`/`UPDATE`/`DROP`/`ATTACH`/multi-statement; enforces the row cap; a known-count query is stable (MRV Semester 1 = 7,702 delivered session rows).
- `tests/test_build.py` — Excel-serial → timestamp conversion (a known serial maps to a known date); `deviation` view returns the expected MRV overlap (1,174 units).
- `tests/test_agent.py` — a ~10-question golden set with the OpenRouter call mocked, asserting tool-call shape and that answers cite SQL. Live-model accuracy is judged by the feedback loop, not unit tests.

## 10. Deliberate simplifications (YAGNI)

- No vector search / embeddings — notes and examples are small enough to inject wholesale.
- No auth in the app itself — Streamlit Cloud viewer restriction is the access control.
- No multi-user session state or conversation persistence — chat history lives in `st.session_state` for the session only.
- No agent-written charts in v1 — text answers + tables. Add plots once the questions being asked are known.
- No Postgres — DuckDB rebuilt at startup, per the parent design doc's upgrade path.

## 11. Phasing

1. **Data**: `build_delivered.py`, `build_designed.py`, `load_duckdb.py` extensions + views. *Done when:* the `deviation` view reproduces the MRV numbers we already computed by hand (1,174 overlap, 154 dropped).
2. **Agent core**: `db.py` guardrails + `agent.py` loop, driven from a CLI. *Done when:* the golden-set questions answer correctly with valid SQL.
3. **UI + loop**: `app.py` chat, per-response feedback, Sheets memory. *Done when:* a 👍 example and a 👎 note both visibly change a subsequent answer.
4. **Deploy**: private repo, Streamlit Cloud, secrets, viewer allowlist.

## 12. Open questions

1. **Which OpenRouter model** for the agent? Needs tool-calling + decent SQL. To be picked by running the golden set against 2–3 candidates on accuracy vs cost.
2. **Who owns the Google service account / Sheet** for the memory store?
3. **Auto-promote or curate?** Should 👍 auto-promote a question→SQL pair into few-shot, or should a human approve it first? Default assumed: auto-promote, since the pair is only reachable if it already produced a good answer.
4. **Sem 1 only, or Sem 1 + 2?** Delivered data has both; designed exports we hold are Sem 1.
