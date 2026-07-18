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
# per-section, then ratings, then standards. A live S-VYASA planning question used all
# 16 slots (universities with no pre-solved view do more exploratory queries), so give
# headroom to avoid truncating a real investigation. Lookups still finish in 1-2.
MAX_TOOL_ITERS = 22
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
When asked for a better/revised plan, HLID, schedule or sequence, the deliverable is **the artifact itself, filled in, in the same shape as the original** — something the reader can hand to someone else and act on. A list of changes is not the artifact. Every number must trace to evidence (actual delivery, the standards) or be flagged as a judgement call. Never write "TBD" — decide, and say what would change your mind.

### Required output structure for a better HLID / plan critique
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

Then a short honest note on what would make it wrong.

**Judgement rules for the artifact:** plan to what delivery actually achieved, not to the aspiration — if a course needed 18 weeks, give it 18. Stagger starts in the order they really began. Target ~90-93% utilisation, never 100%: the buffer is what absorbs disruption. Where a course collapsed (delivered ≪ planned), either give it a genuine window or cut it and say so — do not restate the fantasy.

### Planning for ANY university, including next semester
This works per-university, grounded in that university's OWN delivery history — not a prior plan — so it applies even to universities with no designed data. The full method (which inputs to weigh, the holiday derivation, the grounding rule) is in the data notes under "Designing or critiquing a plan for ANY university". Two things are non-negotiable:
- **Check the plan against all 11 rows of `scheduling_rules`.** They are binding. Name any the plan breaks. (`Maintain Uniform Curriculum Pacing` alone catches most overruns.)
- **Use the university's own course names.** Do not rename across universities — "Web Technologies" and "Web Application Development" may be the same content at different colleges, but each keeps its own label.
"""


class OpenRouterError(Exception):
    pass


def account_usage(api_key):
    """OpenRouter key balance: {usage, limit, remaining} in dollars, or None on failure."""
    try:
        r = requests.get("https://openrouter.ai/api/v1/auth/key",
                         headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
        d = r.json().get("data", {})
        return {"usage": d.get("usage"), "limit": d.get("limit"),
                "remaining": d.get("limit_remaining"), "daily": d.get("usage_daily")}
    except (requests.RequestException, ValueError, KeyError):
        return None


def _accrue(spend, data):
    """Add one completion's usage (real cost + tokens) to the running total."""
    u = data.get("usage") or {}
    spend["cost"] += u.get("cost") or 0.0
    spend["prompt_tokens"] += u.get("prompt_tokens") or 0
    spend["completion_tokens"] += u.get("completion_tokens") or 0


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
    """Answer a question. Returns (text, sql_trace, spend).

    sql_trace is the queries actually run (the UI shows its working). spend is
    {cost, prompt_tokens, completion_tokens} summed across every model call in the
    tool loop — real dollars from OpenRouter, so usage can be tracked live.
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

    # usage:{include} makes OpenRouter return real cost per call; we sum it.
    base = {"model": model, "tools": TOOLS, "usage": {"include": True}}
    spend = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
    sql_trace = []
    try:
        for _ in range(MAX_TOOL_ITERS):
            data = _post({**base, "messages": messages}, api_key)
            _accrue(spend, data)
            msg = data["choices"][0]["message"]
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                return (msg.get("content") or "").strip(), sql_trace, spend

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
        data = _post({**base, "messages": messages + [{
            "role": "user",
            "content": "Answer now with what you have. Say explicitly that the investigation was truncated.",
        }]}, api_key)
        _accrue(spend, data)
        return (data["choices"][0]["message"].get("content") or "").strip(), sql_trace, spend
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
