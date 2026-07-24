"""Chat page — ask the copilot anything about the academic data.

Behaviour unchanged from the original single-page app; only moved into render()
and wired to aip.dashboard for the shared DB/secret/account helpers.
"""
import datetime

import streamlit as st

from aip import agent, dashboard, export

# Cost/capability ladder, cheapest first — the slider order. All support tool-calling.
# Non-Anthropic tiers route through OpenRouter too; slugs were verified live against the
# OpenRouter models API (all report `tools` support). Caveat: "supports tools" is not the
# same as doing 20-step tool use WELL on a planning task — test before trusting for HLIDs.
# ponytail: update a slug if the family bumps its version (they move fast).
MODEL_TIERS = [
    ("DeepSeek V4-Pro", "deepseek/deepseek-v4-pro",    "$0.43/$0.87 · cheapest, 1M ctx — value pick"),
    ("GLM 5.2",         "z-ai/glm-5.2",                "$0.80/$2.53 · cheap, 1M ctx"),
    ("Haiku 4.5",       "anthropic/claude-haiku-4.5",  "$1/$5 · fast — counts and lookups"),
    ("Kimi K3",         "moonshotai/kimi-k3",          "$3/$15 · premium (~Opus price, not cheap)"),
    ("Sonnet 4.5",      "anthropic/claude-sonnet-4.5", "$3/$15 · balanced — most questions"),
    ("Opus 4.6",        "anthropic/claude-opus-4.6",   "$5/$25 · deep analysis"),
    ("Opus 4.7",        "anthropic/claude-opus-4.7",   "$5/$25 · deep analysis, newer"),
    ("Opus 4.8",        "anthropic/claude-opus-4.8",   "$5/$25 · deepest — planning, HLIDs, advisory"),
]
TIER_MODEL = {name: model for name, model, _ in MODEL_TIERS}

DEFAULT_COLLEGE = "S-VYASA"   # fallback for a starter template with no sample college

# Starter prompts: (template, sample_college). {c} fills with each starter's own sample
# college, so the landing spans a MIX of colleges instead of the same one everywhere.
STARTERS = {
    "📋 Plan a semester": [
        ("Design a semester for {c} based on their past delivery and feedback, fixing the issues they had.", "Aurora University"),
        ("Is {c}'s planned course load within the 495-hour AICTE budget?", "Malla Reddy Vishwavidyapeeth"),
    ],
    "🔍 Diagnose a college": [
        ("What went wrong for {c}? Combine the recorded issues and what the delivery data shows.", "Chaitanya Deemed-to-be University"),
        ("Which {c} courses were delivered late or under-delivered versus plan?", "S-VYASA"),
    ],
    "📚 Look up the data": [
        ("How many coding questions exist per course?", None),
        ("Which sessions at {c} rated below 3 for teaching quality?", "NIAT Chevella"),
        ("Which 5 instructors have the lowest session completion rate?", None),
    ],
}


def render():
    con = dashboard.conn()
    api_key = dashboard.secret("OPENROUTER_API_KEY")

    if "msgs" not in st.session_state:
        st.session_state.msgs = []       # [{role, content}]
    if "pending" not in st.session_state:
        st.session_state.pending = None  # a starter chip queues a question here

    with st.sidebar:
        # Model picker: ONE collapsed panel — closed by default, showing the current model.
        # Click to open -> a single radio group of all models; the selected circle fills blue
        # (theme primaryColor in .streamlit/config.toml). Picking one reruns and re-collapses.
        configured = dashboard.secret("AIP_MODEL", agent.DEFAULT_MODEL)
        names = [n for n, _, _ in MODEL_TIERS]
        start = next((n for n, m, _ in MODEL_TIERS if m == configured), "Opus 4.8")
        if st.session_state.get("model_name") not in names:
            st.session_state.model_name = start
        with st.expander(f"Model — {st.session_state.model_name}", expanded=False):
            picked = st.radio("Model", names,
                              index=names.index(st.session_state.model_name),
                              label_visibility="collapsed")
            if picked != st.session_state.model_name:
                st.session_state.model_name = picked
                st.rerun()
        tier = st.session_state.model_name
        model = TIER_MODEL[tier]

        st.divider()
        st.markdown("**Usage**")
        session_cost = sum(m.get("cost", 0) for m in st.session_state.msgs if m["role"] == "assistant")
        acct = dashboard.account(api_key) if api_key else None
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

        if st.button("Clear chat", width="stretch"):
            st.session_state.msgs = []
            st.rerun()

    st.title("🎓 NIAT Learning Copilot")

    if not api_key:
        st.error("No `OPENROUTER_API_KEY` set. Add it to `.streamlit/secrets.toml` "
                 "locally, or to Secrets on Streamlit Cloud.")
        st.stop()

    # Landing: clickable starters, only when the chat is empty.
    if not st.session_state.msgs:
        st.markdown("#### What can I help you with?")
        st.caption("Pick one to start, or type your own below. "
                   "Planning questions do best on the Opus setting.")
        for group, prompts in STARTERS.items():
            st.markdown(f"**{group}**")
            filled = [tmpl.format(c=(sample or DEFAULT_COLLEGE)) for tmpl, sample in prompts]
            cols = st.columns(len(filled))
            for col, prompt in zip(cols, filled):
                if col.button(prompt, key=f"starter::{prompt}", width="stretch"):
                    st.session_state.pending = prompt
                    st.rerun()

    for i, m in enumerate(st.session_state.msgs):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m["role"] == "assistant" and not m["content"].startswith("❌"):
                stem = export.slug(m.get("q", "answer"))
                today = datetime.date.today().isoformat()
                d1, d2, _ = st.columns([1, 1, 5])
                d1.download_button(
                    "⬇ HTML", key=f"html::{i}",
                    data=export.to_html(m["content"], m.get("q", ""), today),
                    file_name=f"{stem}.html", mime="text/html",
                    help="Formatted, printable, opens in any browser — best for sharing.",
                )
                d2.download_button(
                    "⬇ Markdown", key=f"md::{i}",
                    data=m["content"], file_name=f"{stem}.md", mime="text/markdown",
                    help="Raw text — for GitHub, editors, or pasting elsewhere.",
                )
                if m.get("cost"):
                    st.caption(f"{m.get('model', '').split('/')[-1]} · "
                               f"${m['cost']:.4f} · {m.get('tokens', 0):,} tokens")
                # After a grounded plan, offer the opt-in "What could be better" view.
                # Heuristic gate: a plan closes with "utilisation"/"HLID"; skip if the
                # answer already IS that view (avoids a self-referential button).
                content = m["content"]
                is_plan = ("utilisation" in content or "HLID" in content
                           or "Inputs & grounding" in content)
                already_shown = ("what could be better" in content.lower()
                                 or "the one bet" in content.lower())
                if is_plan and not already_shown:
                    if st.button("🔍 What could be better", key=f"wcb::{i}",
                                 help="Opt-in bolder view: changes across plan, pedagogy, "
                                      "structure and standards, optimised for placement readiness."):
                        st.session_state.pending = (
                            'Now give the unconstrained "what could be better" view for the plan '
                            "above — the labelled [evidence]/[recommendation] table across academic "
                            "plan, pedagogy, academic structure and planning standards, optimised "
                            'for placement readiness, closing with "the one bet".'
                        )
                        st.rerun()

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
        spend = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
        with st.chat_message("assistant"), st.spinner("Querying the data…"):
            try:
                text, _, spend = agent.answer(question, history=history, api_key=api_key, model=model, con=con)
            except agent.OpenRouterError as e:
                text = f"❌ Could not reach the model: {e}"
        st.session_state.msgs.append({
            "role": "assistant", "content": text, "q": question,
            "cost": spend["cost"], "model": model,
            "tokens": spend["prompt_tokens"] + spend["completion_tokens"],
        })
        st.rerun()
