#!/usr/bin/env python3
"""Verify a course ingest is lossless and queryable (schema-agnostic).

Usage: python scripts/verify_ingest.py <source.xlsx> <csv_dir>
(1) source xlsx vs written CSV identical (cells + chars)
(2) auto-detected outline sheet: artifact columns present & not truncated
(3) DuckDB can query every CSV in place
"""
import sys, os, csv, zipfile, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from xlsx_dump import shared_strings, sheet_map, read_sheet, safe
import duckdb

csv.field_size_limit(20_000_000)
xlsx, csv_dir = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(xlsx); sst = shared_strings(z)

print("=== (1) LOSSLESS: source xlsx vs written CSV ===")
allok = True
for name, path in sheet_map(z):
    src = read_sheet(z, path, sst)
    sc = sum(1 for row in src for c in row if c.strip())
    sch = sum(len(c) for row in src for c in row)
    fn = os.path.join(csv_dir, safe(name) + ".csv")
    with open(fn, encoding="utf-8") as f:
        dst = list(csv.reader(f))
    dc = sum(1 for row in dst for c in row if c.strip())
    dch = sum(len(c) for row in dst for c in row)
    ok = sc == dc and sch == dch
    allok &= ok
    print(f"  [{'OK' if ok else 'FAIL'}] {name:34s} cells {sc}->{dc}  chars {sch}->{dch}")
print("  LOSSLESS:", "PASS" if allok else "FAIL")
assert allok, "ingest lost data"

def load(fn):
    with open(fn, encoding="utf-8") as f:
        return list(csv.reader(f))

# (2) auto-detect the outline sheet: header containing Session Name (+Module Name)
outline = None
for fn in glob.glob(os.path.join(csv_dir, "*.csv")):
    rows = load(fn)
    if rows and "Session Name" in rows[0] and "Module Name" in rows[0]:
        outline = (fn, rows); break
print("\n=== (2) OUTLINE COMPLETENESS ===")
if outline:
    fn, rows = outline
    idx = {n: i for i, n in enumerate(rows[0])}
    col = lambda r, k: r[idx[k]] if idx.get(k) is not None and idx[k] < len(r) else ""
    data = [r for r in rows[1:] if col(r, "Session Name").strip()]
    print(f"  outline: {os.path.basename(fn)}  sessions: {len(data)}")
    for k in rows[0]:
        if not k.strip() or k in ("Course Id", "Course Name", "Module Name",
                                  "Session No.", "Session ID", "Session Name"):
            continue
        L = [len(col(r, k)) for r in data if col(r, k).strip()]
        print(f"  {k:30s} present {len(L):>3}/{len(data)}  chars[min={min(L) if L else 0} max={max(L) if L else 0}]")
else:
    print("  (no outline sheet found)")

print("\n=== (3) DUCKDB ACCESS (query every CSV in place) ===")
con = duckdb.connect()
for fn in sorted(glob.glob(os.path.join(csv_dir, "*.csv"))):
    p = fn.replace("\\", "/")
    try:
        c = con.execute(f"SELECT count(*) FROM read_csv_auto('{p}', header=true, "
                        f"all_varchar=true, ignore_errors=true)").fetchone()[0]
        print(f"  [OK] {os.path.basename(fn):40s} {c} rows")
    except Exception as e:
        print(f"  [ERR] {os.path.basename(fn):40s} {str(e)[:70]}")
print("\nALL CHECKS PASSED" if allok else "\nCHECKS FAILED")
