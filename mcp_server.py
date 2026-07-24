"""MCP server for the Academic Intelligence Platform.

Exposes the same read-only SQL capability the Streamlit agent uses, so ANY MCP
client (Claude Desktop, Cursor, a Claude.ai custom connector, ...) can query the
academic data with its own LLM -- no OpenRouter key needed on this path.

Thin wrapper over aip/db.py: that module already enforces read-only at the engine,
rejects multi-statement / non-SELECT SQL, and times out runaway queries.

Run locally (stdio, for Claude Desktop / Cursor):   python mcp_server.py
Run as a remote connector (HTTP):                   python mcp_server.py --http

Auth: Claude.ai custom connectors can't send a static token (they use OAuth or
connect open), so the HTTP server runs OPEN unless AIP_MCP_TOKEN is set. Set that
env var only for header-capable clients (Cursor etc.); leave it unset for Claude.ai.
This repo's data is already public, so an open read-only endpoint exposes nothing new.
"""
import os
import sys

# Resolve data + docs against THIS file, so the server works from any cwd
# (MCP clients launch it with an arbitrary working directory).
ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("AIP_DB", os.path.join(ROOT, "data", "aip.duckdb"))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from aip import db  # noqa: E402

mcp = FastMCP(
    "aip",
    instructions=(
        "Academic Intelligence Platform: NIAT/NxtWave academic data (what was "
        "planned, delivered, its content, and student feedback) in one DuckDB store. "
        "Call guide() and describe_schema() BEFORE writing SQL -- the join keys are "
        "non-obvious and a naive join gives a confidently wrong answer. Then use "
        "run_sql() (read-only SELECT/WITH only). guide() also carries the academic-"
        "planning contract: you can generate a 2026-batch HLID + week-by-week academic "
        "calendar when given a start date, end date, and subject list, grounded in the "
        "university's own delivery history. When a plan is asked for but a material input "
        "(start, end, subjects, semester, goal) is missing, ASK before assuming. Deliver "
        "the grounded plan by default and only OFFER an unconstrained 'what could be better' "
        "view (optimised for placement readiness) -- produce it as a separate follow-up "
        "only if the user asks ('unconstrained view' / 'what could be better'). "
        "guide() ALSO carries a second product as "
        "reference context -- the GRIT 2026-27 programme (skills/Miles/tracks); GRIT has "
        "no tables, so answer GRIT questions from the guide, not run_sql()."
    ),
)

MAX_DISPLAY_ROWS = 200


def _load(*names):
    parts = []
    for n in names:
        p = os.path.join(ROOT, "docs", n)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                parts.append(f.read())
    return "\n\n---\n\n".join(parts)


@mcp.tool()
def guide() -> str:
    """The join contract, data caveats, and ready-made query recipes. Read this
    FIRST -- it is what stops a plausible-but-wrong join."""
    return _load("data-notes.md", "examples.md", "planning-method.md", "grit-programme.md")


@mcp.tool()
def describe_schema() -> str:
    """Live schema: every table/view with its columns, types, and row count."""
    return db.schema_text()


@mcp.tool()
def run_sql(query: str) -> str:
    """Run one read-only SQL query (SELECT/WITH only) and return the rows as a
    table. Writes, DDL, and multi-statement input are rejected at the engine."""
    try:
        cols, rows, truncated = db.run_sql(query)
    except db.QueryError as e:
        return f"QUERY REJECTED: {e}"  # fed back so the model can repair
    if not rows:
        return "(0 rows)"
    lines = [" | ".join(cols)]
    for r in rows[:MAX_DISPLAY_ROWS]:
        lines.append(" | ".join("" if c is None else str(c)[:80] for c in r))
    note = []
    if len(rows) > MAX_DISPLAY_ROWS:
        note.append(f"showing {MAX_DISPLAY_ROWS} of {len(rows)} rows")
    if truncated:
        note.append("result capped at 1000 rows -- add LIMIT or aggregate")
    if note:
        lines.append(f"[{'; '.join(note)}]")
    return "\n".join(lines)


@mcp.resource("aip://guide")
def guide_resource() -> str:
    """Same content as guide(), for clients that read resources."""
    return _load("data-notes.md", "examples.md", "planning-method.md", "grit-programme.md")


class _BearerAuth:
    """Pure-ASGI bearer gate (no response buffering, unlike BaseHTTPMiddleware).
    /healthz stays open for the health probe."""
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") != "/healthz":
            headers = dict(scope.get("headers") or [])
            if headers.get(b"authorization", b"").decode() != f"Bearer {self.token}":
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await self.app(scope, receive, send)


def _http_app():
    """Starlette app for remote serving: MCP at /mcp, an open /healthz for Render's
    probe, optional bearer auth. DNS-rebinding protection is OFF -- it guards LOCAL
    servers against browser rebinding; a public Render deployment is reached by
    non-local hosts by design, so the Host check must not 421 them."""
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app()

    async def healthz(_request):
        return PlainTextResponse("ok")
    # Prepend so it wins over the /mcp mount regardless of route ordering.
    app.router.routes.insert(0, Route("/healthz", healthz, methods=["GET"]))

    token = os.environ.get("AIP_MCP_TOKEN")
    if token:
        app.add_middleware(_BearerAuth, token=token)
    return app


if __name__ == "__main__":
    if "--http" in sys.argv:
        # Remote connector: bind 0.0.0.0:$PORT for Render; the MCP endpoint is /mcp.
        import uvicorn
        uvicorn.run(_http_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
    else:
        mcp.run(transport="stdio")
