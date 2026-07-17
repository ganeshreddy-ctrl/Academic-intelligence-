#!/usr/bin/env python3
"""Convert an .xlsx to one CSV per sheet, stdlib only. Prints a structure summary.

Usage: python scripts/xlsx_dump.py <file.xlsx> <out_dir>
ponytail: stdlib zipfile+xml, no openpyxl/pandas. Handles shared+inline strings.
"""
import csv, re, sys, zipfile, os
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

def col_to_idx(ref):  # "AB12" -> 27 (0-based col)
    letters = re.match(r"[A-Z]+", ref).group()
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1

def shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root:
        out.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    return out

def sheet_map(z):
    """ordered [(name, worksheet_path)] following workbook + rels."""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {r.get("Id"): r.get("Target") for r in rels}
    out = []
    for s in wb.find(f"{NS}sheets"):
        rid = s.get(f"{RNS}id")
        tgt = rid_to_target[rid]
        path = "xl/" + tgt if not tgt.startswith("/") else tgt.lstrip("/")
        out.append((s.get("name"), path))
    return out

def read_sheet(z, path, sst):
    root = ET.fromstring(z.read(path))
    data = root.find(f"{NS}sheetData")
    rows = []
    maxcol = 0
    for r in data.findall(f"{NS}row"):
        cells = {}
        for c in r.findall(f"{NS}c"):
            ref, t = c.get("r"), c.get("t")
            ci = col_to_idx(ref)
            maxcol = max(maxcol, ci)
            if t == "s":
                v = c.find(f"{NS}v")
                val = sst[int(v.text)] if v is not None else ""
            elif t == "inlineStr":
                is_ = c.find(f"{NS}is")
                val = "".join(x.text or "" for x in is_.iter(f"{NS}t")) if is_ is not None else ""
            else:
                v = c.find(f"{NS}v")
                val = v.text if v is not None else ""
            cells[ci] = val
        rows.append(cells)
    return [[row.get(i, "") for i in range(maxcol + 1)] for row in rows]

def safe(name):
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()

def main():
    xlsx, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    z = zipfile.ZipFile(xlsx)
    sst = shared_strings(z)
    for name, path in sheet_map(z):
        rows = read_sheet(z, path, sst)
        fn = os.path.join(out_dir, safe(name) + ".csv")
        with open(fn, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        header = rows[0] if rows else []
        print(f"\n### {name}  ->  {os.path.basename(fn)}")
        print(f"    rows={len(rows)} (incl header)  cols={len(header)}")
        print(f"    columns: {[h[:40] for h in header]}")

if __name__ == "__main__":
    main()
