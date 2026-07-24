"""NIAT Learning Copilot — dashboard router.

Three pages: Chat (ask the data), Knowledge Base (per-university catalog), and
Pipeline (how the data is built). Shared infra lives in aip/dashboard.py.

Run locally:  streamlit run app.py
Deploy:       Streamlit Cloud, with secrets OPENROUTER_API_KEY / AIP_MODEL.
"""
import streamlit as st

from aip import dashboard
from views import chat, knowledge_base, pipeline

st.set_page_config(page_title="NIAT Learning Copilot", page_icon="🎓", layout="wide")

dashboard.require_login()   # Google OIDC gate — Nxtwave accounts only; renders before any page

dashboard.db_path()      # build the DB once per boot (cached)
dashboard.inject_css()

# Explicit url_path per page: all three callables are named `render`, and Streamlit
# infers the pathname from the callable name, which would collide.
pg = st.navigation([
    st.Page(chat.render, title="Chat", icon="💬", url_path="chat", default=True),
    st.Page(knowledge_base.render, title="Knowledge Base", icon="📚", url_path="knowledge-base"),
    st.Page(pipeline.render, title="Pipeline", icon="🔧", url_path="pipeline"),
])
pg.run()
