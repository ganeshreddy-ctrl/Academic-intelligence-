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
    for f in sorted(glob.glob("data/canonical/**/*", recursive=True) + ["data/courses.csv"]):
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


def inject_css():
    """Light visual polish — Streamlit is templated by default."""
    st.markdown("""<style>
.stButton>button, .stDownloadButton>button { border-radius: 8px; }
.stButton>button { font-weight: 400; }
div[data-testid="stChatMessage"] { padding-top: .3rem; padding-bottom: .3rem; }
section[data-testid="stSidebar"] div[data-testid="stMetric"] { padding: 2px 0; }
</style>""", unsafe_allow_html=True)
