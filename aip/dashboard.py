"""Shared UI infrastructure for the multi-page dashboard.

Everything the pages need in common: secrets, the DuckDB build/connection pattern,
table counts, the OpenRouter account lookup, and CSS. Extracted from the original
single-page app.py so Chat / Knowledge Base / Pipeline can all reuse it.
"""
import glob
import hashlib
import os
import tempfile

import duckdb
import streamlit as st

from . import agent


def secret(name, default=None):
    """Streamlit Cloud secrets, falling back to env for local runs."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # noqa: BLE001 - no secrets.toml locally is fine
        pass
    return os.environ.get(name, default)


def _data_fingerprint():
    """A cheap hash of the committed data files. Changes whenever a deploy pulls new
    CSVs/parquet — which is what must trigger a rebuild."""
    parts = []
    for f in sorted(glob.glob("data/canonical/**/*", recursive=True)):
        if os.path.isfile(f):
            parts.append(f"{os.path.basename(f)}:{os.path.getsize(f)}:{os.path.getmtime(f):.0f}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


@st.cache_resource(show_spinner="Building the data store…")
def _build_db(fingerprint):
    """Build the DB into a path keyed by the DATA fingerprint. Because the cache key is
    the fingerprint, a data change forces a rebuild even if Streamlit Cloud keeps the
    process (and this cache) alive across a deploy — the failure mode where a stale DB,
    built before a new table existed, kept being served and raised CatalogException.
    A fresh per-fingerprint path also avoids DuckDB's file-lock / stale-WAL conflicts.
    """
    import scripts.load_duckdb as loader
    path = os.path.join(tempfile.gettempdir(), f"aip_{os.getpid()}_{fingerprint}.duckdb")
    loader.build(path, verbose=False)
    return path


def db_path():
    return _build_db(_data_fingerprint())


def conn():
    """A fresh read-only connection, never cached. Cheap, and many read-only readers to
    one file are safe — unlike a single cached connection, which DuckDB (not thread-safe)
    corrupts when Streamlit shares it across concurrent session threads."""
    return duckdb.connect(db_path(), read_only=True)


@st.cache_data(ttl=600, show_spinner=False)
def table_counts():
    """Table names + row counts, computed once (not on every rerun) on an isolated
    connection. Returns [(name, rows), ...]."""
    c = conn()
    try:
        out = []
        for (t,) in c.execute("SHOW TABLES").fetchall():
            row = c.execute(f'SELECT count(*) FROM "{t}"').fetchone()
            out.append((t, row[0] if row else 0))
        return out
    finally:
        c.close()


@st.cache_data(ttl=60, show_spinner=False)
def account(_key):
    """OpenRouter account balance, refreshed at most once a minute (not every rerun)."""
    return agent.account_usage(_key)


_ALLOWED_DOMAINS = ("@nxtwave.co.in", "@nxtwave.tech")


def require_login():
    """Google OIDC gate — only verified Nxtwave accounts pass. Renders the login
    screen and st.stop()s for everyone else. Call before st.navigation so no page
    or sidebar leaks to anonymous users. `str.endswith` accepts a tuple."""
    if st.user.is_logged_in:
        email = (st.user.email or "").lower()
        if st.user.get("email_verified") and email.endswith(_ALLOWED_DOMAINS):
            return
        _login_screen(denied=st.user.email or "That account")
    else:
        _login_screen()
    st.stop()


def _login_screen(denied=None):
    # All visual content lives in ONE self-contained markdown block — Streamlit
    # auto-closes a bare <div>, so wrapping widgets in raw open/close divs breaks.
    st.markdown("""<style>
      header[data-testid="stHeader"], footer { display: none; }
      [data-testid="stAppViewContainer"] {
        background: linear-gradient(160deg,#eaf1ff 0%,#f6f9ff 45%,#ffffff 100%); }
      .block-container { min-height: 94vh; max-width: 640px; padding-top: 0; padding-bottom: 0;
        display: flex; flex-direction: column; justify-content: center; }
      .login-hero { text-align: center; margin-bottom: 1.6rem; }
      .login-hero .logo { display:inline-flex; align-items:center; justify-content:center;
        width:96px; height:96px; font-size:3.2rem; border-radius:26px;
        background:linear-gradient(135deg,#3b82f6,#6366f1);
        box-shadow:0 14px 34px rgba(79,70,229,.38); margin-bottom:1.2rem; }
      .login-hero h1 { font-size:2.3rem; font-weight:800; letter-spacing:-.02em; margin:0 0 .45rem;
        background:linear-gradient(90deg,#1e3a8a,#4f46e5); -webkit-background-clip:text;
        background-clip:text; -webkit-text-fill-color:transparent; }
      .login-hero p { color:#64748b; font-size:1.05rem; margin:0; }
      div.stButton > button { border-radius:12px; padding:.72rem 1rem; font-weight:600;
        box-shadow:0 10px 24px rgba(59,130,246,.30); transition:transform .06s ease; }
      div.stButton > button:hover { transform:translateY(-1px); }
    </style>""", unsafe_allow_html=True)

    logo, title, sub = ("🎓", "NIAT Learning Copilot", "Ask anything about your academic data.")
    if denied:
        logo, title, sub = ("🔒", "Wrong account", f"{denied} can’t sign in here — use your Nxtwave account.")

    _, mid, _ = st.columns([1, 1.5, 1])
    with mid:
        st.markdown(
            f"<div class='login-hero'><div class='logo'>{logo}</div>"
            f"<h1>{title}</h1><p>{sub}</p></div>",
            unsafe_allow_html=True)
        if denied:
            st.button("Try another account", on_click=st.logout, use_container_width=True)
        else:
            st.button("Continue with Google", on_click=st.login,
                      type="primary", icon=":material/login:", use_container_width=True)


def inject_css():
    """Light visual polish — Streamlit is templated by default."""
    st.markdown("""<style>
.stButton>button, .stDownloadButton>button { border-radius: 8px; }
.stButton>button { font-weight: 400; }
div[data-testid="stChatMessage"] { padding-top: .3rem; padding-bottom: .3rem; }
section[data-testid="stSidebar"] div[data-testid="stMetric"] { padding: 2px 0; }
</style>""", unsafe_allow_html=True)
