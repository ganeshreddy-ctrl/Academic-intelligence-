"""OpenRouter tool-calling agent: answers questions by querying DuckDB read-only.

One tool (run_sql) covers every question shape — analytics are aggregations,
content lookup is a select, advisory is query-then-reason. The prompt is
deliberately schema-heavy and instruction-light: breadth of coverage comes from
the agent knowing the data, not from task-specific prompting.
"""
import json
import os
import pathlib
import time

import requests

from . import db

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Opus for synthesis. Advisory answers ("give me a better HLID") are where the tier
# shows; sonnet-4.5 handled lookups fine but produced thinner analysis. ~1.7x the cost
# of sonnet-4.5 ($5/$25 vs $3/$15 per M tok) — override with AIP_MODEL if that matters.
DEFAULT_MODEL = "anthropic/claude-opus-4.8"
# Analytical questions need a chain of dependent queries: plan, then actuals, then
# per-section, then ratings, then standards. At 5 the agent ran out mid-investigation
# and answered from partial evidence ("Investigation truncated..."). The pre-solved
# course_plan_vs_actual view now collapses most of that into one query; this is headroom.
MAX_TOOL_ITERS = 16
NOTES_PATH = pathlib.Path(__file__).resolve().parents[1] / "docs" / "data-notes.md"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": (
            "Run a read-only SQL query (DuckDB dialect) against the academic data store "
            "and get rows back. Only SELECT/WITH is permitted. Use this for every factual "
            "claim — never state a number that did not come from a query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A single DuckDB SELECT/WITH statement."}
            },
            "required": ["query"],
        },
    },
}]


def _notes() -> str:
    try:
        return NOTES_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def system_prompt(con=None) -> str:
    return f"""You answer questions about NxtWave's academic data (NIAT programme) for the Gen-AI Content team.

You have one tool: `run_sql`, a read-only DuckDB query. Every factual claim you make must come from a query you actually ran. If you did not query it, do not assert it.

## Live database schema
{db.schema_text(con)}

## Data notes (authoritative — these override any assumption)
{_notes()}

## How to work
- Explore with small queries first if you are unsure of values (e.g. `SELECT DISTINCT ...`).
- Prefer the pre-built views (`deviation`, `delivered_sections`, `session_feedback_safe`, `content_units`) over re-deriving their joins.
- If a query returns nothing, say so — do not substitute a different question's answer.
- If the data cannot answer the question, say that plainly and explain what is missing.

## Every answer must show its reasoning
A bare number is not an acceptable answer — the reader must be able to judge whether to trust it. Structure every response as:

1. **The answer**, lead with it, in plain language.
2. **How you got it** — which tables/views you queried, what you filtered on, and what each number actually counts (e.g. "distinct unit_id, Semester 1 only, sections exploded"). Name the real tables you used.
3. **What affects it** — assumptions you made, and any caveat from the data notes that materially changes how the number should be read. If a caveat applies, state it next to the number, not as a footnote.

Match length to the question: 2-4 sentences of reasoning for a lookup, a full structured analysis for an analytical one. Never skip step 2.

Rules that override brevity:
- Never state a number that did not come from a query you ran.
- If you had to interpret an ambiguous question, say which interpretation you took.
- If the result rests on a known-weak join or partial data (e.g. course crosswalk coverage, Prod-Sequence unit_id coverage), say so in the same breath as the number.
- Distinguish "the data says zero" from "the data does not cover this". They are different answers.

## Analytical and advisory questions
Some questions are not lookups — "what went wrong with X", "give me a better plan", "what should we change". These are the hardest and most valuable. For them:

- **Investigate before concluding.** Run a chain of dependent queries: what was planned, what was delivered, per-section (a student experiences ONE section — raw totals across sections are meaningless), how it was rated, and how it compares to `planning_standards`. One query is never enough for an advisory answer.
- **Always check `planning_standards`.** Whenever a plan is being assessed, judge it against the 90-day / 15-week / 33-hrs-per-week / 495-hour budget. Whether the plan was ever *achievable* usually matters more than how it was executed.
- **Separate the failure modes.** Poor ratings mean a delivery problem; good ratings plus heavy slippage mean a *planning* problem. Say which one the evidence supports — the remedies are completely different.
- **Normalise before comparing.** Per-section, per-week, per-student. Compare like with like.
- **Structure the answer:** what the evidence shows (with numbers) → the recommendation → what would make it wrong. Recommend concrete numbers and dates, not "consider reviewing".
- **Say what you are unsure about.** A derived conversion, a small sample, a known-partial export — name it. An advisory answer that hides its weak points is worse than useless, because it will be acted on.

## "Give me a better X" means BUILD X, not describe how to fix X
When asked for a better/revised plan, HLID, schedule or sequence, the deliverable is **the artifact itself, filled in, in the same shape as the original** — something the reader can hand to someone else and act on. A list of changes is not the artifact.

For a **better HLID** that means an actual table with one row per course and every column the real HLID has:
`Course | Sessions | Session Hours | Practice Hours | Micro Assessment Hours | Start | End | Weeks`
— plus a total row, the utilisation against the 495-hour budget, and concrete dates. Query `designed_course_plan` first to see the exact columns you must reproduce.

Then, separately and briefly, the changes you made and why. Evidence first, artifact second, rationale third.

Every number in the artifact must trace to evidence (actual delivery, the standards) or be flagged as a judgement call. Never leave a cell as "TBD" — decide, and say what would change your mind.
"""


class OpenRouterError(Exception):
    pass


def _post(payload, api_key, retries=3):
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=120,
            )
            if r.status_code == 200:
                return r.json()
            last = f"{r.status_code}: {r.text[:300]}"
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)   # transient — back off and retry
                continue
            raise OpenRouterError(last)   # 4xx: retrying will not help
        except requests.RequestException as e:
            last = str(e)
            time.sleep(2 ** attempt)
    raise OpenRouterError(f"OpenRouter unavailable after {retries} attempts: {last}")


def answer(question, history=None, api_key=None, model=None, con=None):
    """Answer a question. Returns (text, sql_trace).

    sql_trace is the list of queries actually run, so the UI can show its working
    and the feedback log can record exactly what produced the answer.
    """
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise OpenRouterError("No OPENROUTER_API_KEY configured.")
    model = model or os.environ.get("AIP_MODEL", DEFAULT_MODEL)
    own = con is None
    con = con or db.connect()

    messages = [{"role": "system", "content": system_prompt(con)}]
    for turn in (history or []):
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    sql_trace = []
    try:
        for _ in range(MAX_TOOL_ITERS):
            data = _post({"model": model, "messages": messages, "tools": TOOLS}, api_key)
            msg = data["choices"][0]["message"]
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                return (msg.get("content") or "").strip(), sql_trace

            for call in calls:
                try:
                    query = json.loads(call["function"]["arguments"])["query"]
                except (KeyError, ValueError) as e:
                    content = f"Could not parse tool arguments: {e}"
                    query = None
                if query is not None:
                    sql_trace.append(query)
                    try:
                        cols, rows, truncated = db.run_sql(query, con)
                        content = _format(cols, rows, truncated)
                    except db.QueryError as e:
                        # Feed the error back verbatim so the model can repair it.
                        content = f"ERROR: {e}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": content,
                })

        # Iteration cap hit: answer with what we have rather than looping forever.
        data = _post({"model": model, "messages": messages + [{
            "role": "user",
            "content": "Answer now with what you have. Say explicitly that the investigation was truncated.",
        }]}, api_key)
        return (data["choices"][0]["message"].get("content") or "").strip(), sql_trace
    finally:
        if own:
            con.close()


def _format(cols, rows, truncated):
    if not rows:
        return "0 rows."
    head = " | ".join(cols)
    body = "\n".join(" | ".join("" if v is None else str(v) for v in r) for r in rows[:200])
    note = f"\n({len(rows)} rows" + (f", TRUNCATED at {db.ROW_LIMIT}" if truncated else "") + ")"
    if len(rows) > 200:
        note += " [showing first 200]"
    return f"{head}\n{body}{note}"
