#!/usr/bin/env python3
"""Checks for the MCP server (mcp_server.py). Plain-assert runner, like test_db.py.
Run: python tests/test_mcp.py   (needs data/aip.duckdb built)
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_server as srv

fails = []


def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except AssertionError as e:
        fails.append(name)
        print(f"  FAIL  {name}: {e}")


def run_sql_returns_rows():
    out = srv.run_sql("SELECT count(*) AS n FROM college_summary")
    assert "n" in out and out.splitlines()[1].strip().isdigit(), f"bad result: {out!r}"


def write_is_rejected():
    out = srv.run_sql("DROP TABLE college_summary")
    assert out.startswith("QUERY REJECTED"), f"write not rejected: {out!r}"


def multi_statement_rejected():
    out = srv.run_sql("SELECT 1; SELECT 2")
    assert out.startswith("QUERY REJECTED"), f"multi-statement not rejected: {out!r}"


def schema_and_guide_nonempty():
    assert "college_summary" in srv.describe_schema(), "schema missing known table"
    g = srv.guide()
    assert "unit_id" in g and len(g) > 500, "guide missing join-contract content"
    assert "What could be better" in g, "guide missing the unconstrained-view contract"
    assert "Ask before you assume" in g, "guide missing the ask-on-missing-inputs rule"


def tools_registered():
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert {"run_sql", "describe_schema", "guide"} <= names, f"tools missing: {names}"


print("mcp server:")
check("run_sql returns rows", run_sql_returns_rows)
check("write is rejected", write_is_rejected)
check("multi-statement is rejected", multi_statement_rejected)
check("schema + guide non-empty", schema_and_guide_nonempty)
check("tools registered on server", tools_registered)

print()
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all checks passed")
