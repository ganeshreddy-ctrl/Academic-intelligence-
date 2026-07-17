#!/usr/bin/env python3
"""Assemble data/aip.duckdb from the git-committed canonical CSVs + courses.csv.

No raw data needed — this is what makes the repo self-sufficient: a fresh clone
can rebuild the queryable store from what's in git.

Usage: python scripts/load_duckdb.py
"""
import duckdb, glob, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def build(db="data/aip.duckdb", verbose=True):
    if os.path.exists(db):
        os.remove(db)
    con = duckdb.connect(db)
    sources = [("courses", "data/courses.csv")] + [
        (os.path.splitext(os.path.basename(p))[0], p)
        for p in sorted(glob.glob("data/canonical/*.csv"))
    ]
    for name, path in sources:
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM "
                    f"read_csv_auto('{path.replace(os.sep,'/')}', header=true, all_varchar=true)")
    if verbose:
        print("=== aip.duckdb tables (from committed canonical) ===")
        for (t,) in con.execute("SHOW TABLES").fetchall():
            n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n} rows")
    tables = [t for (t,) in con.execute("SHOW TABLES").fetchall()]
    assert "courses" in tables and len(tables) > 1, "no canonical tables loaded"
    con.close()
    return db

if __name__ == "__main__":
    build()
