"""NIAT Learning Copilot — chat over the academic data store.

Run locally:  streamlit run app.py
Deploy:       Streamlit Cloud, with secrets OPENROUTER_API_KEY / AIP_MODEL.
"""
import os

import streamlit as st

from aip import agent, db

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

# Starter prompts, grouped by what the copilot does. Clicking one runs it — the entry
# point that turns a blank chat box into a copilot people can actually start with.
STARTERS = {
    "📋 Plan a semester": [
        "Design Semester 1 for S-VYASA based on their past delivery and feedback, fixing the issues they had.",
        "Is any college's planned course load over the 495-hour AICTE budget?",
    ],
    "🔍 Diagnose a college": [
        "What went wrong for Aurora in Semester 1? Combine the recorded issues and what the delivery data shows.",
        "Which MRV courses were delivered late versus their plan, and by how much?",
    ],
    "📚 Look up the data": [
        "How many coding questions exist per course?",
        "Which sessions at CDU rated below 3 for teaching quality?",
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

# Landing: show what the copilot can do, as clickable starters. Only when the chat is empty.
if not st.session_state.msgs:
    st.markdown("#### What can I help you with?")
    st.caption("Pick one to start, or type your own below. Planning questions do best on the Opus setting.")
    for group, prompts in STARTERS.items():
        st.markdown(f"**{group}**")
        cols = st.columns(len(prompts))
        for col, prompt in zip(cols, prompts):
            if col.button(prompt, key=f"starter::{prompt}", use_container_width=True):
                st.session_state.pending = prompt
                st.rerun()

for m in st.session_state.msgs:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# A question comes from the chat box OR a starter chip; both feed the same path.
typed = st.chat_input("Ask about the academic data…")
question = typed or st.session_state.pending
st.session_state.pending = None

if question:
    st.session_state.msgs.append({"role": "user", "content": question})
    history = [{"role": m["role"], "content": m["content"]}
               for m in st.session_state.msgs[:-1]]
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Querying the data…"):
        try:
            text, _ = agent.answer(question, history=history, api_key=API_KEY, model=MODEL, con=con)
        except agent.OpenRouterError as e:
            text = f"❌ Could not reach the model: {e}"
    st.session_state.msgs.append({"role": "assistant", "content": text})
    st.rerun()
