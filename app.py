"""NIAT Learning Copilot — chat over the academic data store.

Run locally:  streamlit run app.py
Deploy:       Streamlit Cloud, with secrets OPENROUTER_API_KEY / AIP_MODEL.
"""
import datetime
import os

import streamlit as st

from aip import agent, db, export

st.set_page_config(page_title="NIAT Learning Copilot", page_icon="🎓", layout="wide")


def secret(name, default=None):
    """Streamlit Cloud secrets, falling back to env for local runs."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # noqa: BLE001 - no secrets.toml locally is fine
        pass
    return os.environ.get(name, default)


@st.cache_resource
def get_db():
    """Rebuild aip.duckdb from committed data on every boot, then connect read-only.

    ALWAYS rebuild — do not skip when the file exists. Streamlit Cloud keeps the
    container filesystem across restarts, so a "build only if missing" check served a
    database built by older code forever. The rebuild takes ~2.6s and @st.cache_resource
    runs it once per boot.
    """
    import scripts.load_duckdb as loader
    loader.build(db.DB_PATH, verbose=False)
    return db.connect()


con = get_db()
API_KEY = secret("OPENROUTER_API_KEY")

# Light visual polish — Streamlit is templated by default; round the corners, tighten
# spacing, and give the starter buttons a calmer, left-read feel.
st.markdown("""<style>
.stButton>button, .stDownloadButton>button { border-radius: 8px; }
.stButton>button { font-weight: 400; }
div[data-testid="stChatMessage"] { padding-top: .3rem; padding-bottom: .3rem; }
section[data-testid="stSidebar"] div[data-testid="stMetric"] { padding: 2px 0; }
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=60, show_spinner=False)
def account(_key):
    """OpenRouter account balance, refreshed at most once a minute (not every rerun)."""
    return agent.account_usage(_key)

# Cost/capability ladder, cheapest first — the slider order. All support tool-calling
# (verified against OpenRouter's live list), which this agent requires.
MODEL_TIERS = [
    ("Haiku 4.5",  "anthropic/claude-haiku-4.5",  "$1/$5 · fastest, cheapest — counts and lookups"),
    ("Sonnet 4.5", "anthropic/claude-sonnet-4.5", "$3/$15 · balanced — most questions"),
    ("Opus 4.6",   "anthropic/claude-opus-4.6",   "$5/$25 · deep analysis"),
    ("Opus 4.7",   "anthropic/claude-opus-4.7",   "$5/$25 · deep analysis, newer"),
    ("Opus 4.8",   "anthropic/claude-opus-4.8",   "$5/$25 · deepest — planning, HLIDs, advisory"),
]
TIER_MODEL = {name: model for name, model, _ in MODEL_TIERS}
TIER_NOTE = {name: note for name, _, note in MODEL_TIERS}

ALL_COLLEGES = "All colleges"
DEFAULT_COLLEGE = "S-VYASA"   # fills the {c} slot when no specific college is focused


@st.cache_data(show_spinner=False)
def college_list():
    """Real colleges with delivery data, for the focus picker."""
    rows = con.execute("""SELECT institute_name FROM delivered_sessions
        WHERE institute_name IS NOT NULL
        GROUP BY 1 HAVING count(*) > 100 ORDER BY 1""").fetchall()
    return [r[0] for r in rows]


# Starter prompts as templates ({c} = the focused college). Clicking one runs it — the
# entry point that turns a blank chat box into a copilot people can start with.
STARTERS = {
    "📋 Plan a semester": [
        "Design Semester 1 for {c} based on their past delivery and feedback, fixing the issues they had.",
        "Is {c}'s planned course load within the 495-hour AICTE budget?",
    ],
    "🔍 Diagnose a college": [
        "What went wrong for {c} in Semester 1? Combine the recorded issues and what the delivery data shows.",
        "Which {c} courses were delivered late or under-delivered versus plan?",
    ],
    "📚 Look up the data": [
        "How many coding questions exist per course?",
        "Which sessions at {c} rated below 3 for teaching quality?",
        "Which 5 instructors have the lowest session completion rate?",
    ],
}

if "msgs" not in st.session_state:
    st.session_state.msgs = []       # [{role, content}]
if "pending" not in st.session_state:
    st.session_state.pending = None  # a starter chip queues a question here

with st.sidebar:
    st.subheader("🎓 NIAT Learning Copilot")
    st.caption("Ask anything about the academic data — content, courses, delivery, "
               "feedback, instructors, and academic planning for any college.")

    focus = st.selectbox(
        "Focus college",
        [ALL_COLLEGES] + college_list(),
        help="Scope questions and starters to one college. Leave on 'All colleges' "
             "to ask across everything or name a college yourself.",
    )

    # AIP_MODEL picks where the slider starts; the slider is the control from then on.
    configured = secret("AIP_MODEL", agent.DEFAULT_MODEL)
    start = next((n for n, m, _ in MODEL_TIERS if m == configured), "Opus 4.8")
    name_slot = st.empty()   # filled after the widget with the resolved model id
    tier = st.select_slider(
        "Model",
        options=[n for n, _, _ in MODEL_TIERS],
        value=start,
        help="Slide right for deeper analysis, left for speed and lower cost.",
        label_visibility="collapsed",
    )
    MODEL = TIER_MODEL[tier]
    name_slot.markdown(f"**Model** &nbsp; `{MODEL}`")
    st.caption(TIER_NOTE[tier])
    if tier.startswith("Haiku"):
        st.caption("⚠️ Fine for lookups, weaker on multi-step analysis — "
                   "slide to Opus for planning questions.")

    with st.expander("What each model is for"):
        for name, _model, note in MODEL_TIERS:
            price, _, purpose = note.partition("·")
            st.markdown(f"**{name}** — {purpose.strip()}  \n`{price.strip()}` per 1M tokens (in/out)")

    st.divider()

    # --- Usage & cost (what the team asked to track) ---
    st.markdown("**Usage**")
    session_cost = sum(m.get("cost", 0) for m in st.session_state.msgs if m["role"] == "assistant")
    acct = account(API_KEY) if API_KEY else None
    c1, c2 = st.columns(2)
    c1.metric("This session", f"${session_cost:.3f}")
    if acct and acct.get("usage") is not None:
        c2.metric("Key spent", f"${acct['usage']:.2f}")
        if acct.get("limit"):
            frac = min(1.0, acct["usage"] / acct["limit"])
            st.progress(frac, text=f"${acct['usage']:.2f} of ${acct['limit']:.0f}"
                                    f" · ${acct.get('remaining') or 0:.2f} left")
        if acct.get("daily") is not None:
            st.caption(f"Today: ${acct['daily']:.2f}")
    else:
        c2.metric("Key spent", "—", help="Add credit / a valid key to see account usage.")

    st.divider()

    tables = [t for (t,) in con.execute("SHOW TABLES").fetchall()]
    with st.expander(f"Data ({len(tables)} tables)"):
        for t in tables:
            n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            st.write(f"`{t}` — {n:,}")
    if st.button("Clear chat", use_container_width=True):
        st.session_state.msgs = []
        st.rerun()

st.title("🎓 NIAT Learning Copilot")

if not API_KEY:
    st.error("No `OPENROUTER_API_KEY` set. Add it to `.streamlit/secrets.toml` "
             "locally, or to Secrets on Streamlit Cloud.")
    st.stop()

# The college that fills {c} in starters and scopes free-typed questions.
focus_college = DEFAULT_COLLEGE if focus == ALL_COLLEGES else focus

# Landing: show what the copilot can do, as clickable starters. Only when the chat is empty.
if not st.session_state.msgs:
    st.markdown("#### What can I help you with?")
    scope_note = (f"Focused on **{focus}**. " if focus != ALL_COLLEGES else "")
    st.caption(scope_note + "Pick one to start, or type your own below. "
               "Planning questions do best on the Opus setting.")
    for group, prompts in STARTERS.items():
        st.markdown(f"**{group}**")
        filled = [p.format(c=focus_college) for p in prompts]
        cols = st.columns(len(filled))
        for col, prompt in zip(cols, filled):
            if col.button(prompt, key=f"starter::{prompt}", use_container_width=True):
                st.session_state.pending = prompt
                st.rerun()

for i, m in enumerate(st.session_state.msgs):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        # Export lives under each answer: an answer is often a plan someone needs to share.
        if m["role"] == "assistant" and not m["content"].startswith("❌"):
            stem = export.slug(m.get("q", "answer"))
            today = datetime.date.today().isoformat()
            c1, c2, _ = st.columns([1, 1, 5])
            c1.download_button(
                "⬇ HTML", key=f"html::{i}",
                data=export.to_html(m["content"], m.get("q", ""), today),
                file_name=f"{stem}.html", mime="text/html",
                help="Formatted, printable, opens in any browser — best for sharing.",
            )
            c2.download_button(
                "⬇ Markdown", key=f"md::{i}",
                data=m["content"], file_name=f"{stem}.md", mime="text/markdown",
                help="Raw text — for GitHub, editors, or pasting elsewhere.",
            )
            if m.get("cost"):
                st.caption(f"{m.get('model', '').split('/')[-1]} · "
                           f"${m['cost']:.4f} · {m.get('tokens', 0):,} tokens")

# A question comes from the chat box OR a starter chip; both feed the same path.
typed = st.chat_input("Ask about the academic data…")
question = typed or st.session_state.pending
st.session_state.pending = None

if question:
    st.session_state.msgs.append({"role": "user", "content": question})
    history = [{"role": m["role"], "content": m["content"]}
               for m in st.session_state.msgs[:-1]]
    # Scope a free-typed question to the focused college — but only softly, and only if
    # the user didn't already name a college, so a cross-college question still works.
    effective = question
    if focus != ALL_COLLEGES and focus.lower() not in question.lower():
        effective = (f"{question}\n\n(Assume this is about {focus} unless another "
                     f"college is named.)")
    with st.chat_message("user"):
        st.markdown(question)
    spend = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
    with st.chat_message("assistant"), st.spinner("Querying the data…"):
        try:
            text, _, spend = agent.answer(effective, history=history, api_key=API_KEY, model=MODEL, con=con)
        except agent.OpenRouterError as e:
            text = f"❌ Could not reach the model: {e}"
    st.session_state.msgs.append({
        "role": "assistant", "content": text, "q": question,
        "cost": spend["cost"], "model": MODEL,
        "tokens": spend["prompt_tokens"] + spend["completion_tokens"],
    })
    st.rerun()
