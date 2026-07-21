#!/usr/bin/env python3
"""Flatten the HLID + Recommended Prod Sequence xlsx into committed 'designed' tables.

Writes:
  data/canonical/planning/designed/designed_sequence.csv     — unit-level plan: what was meant to run, when
  data/canonical/planning/designed/designed_course_plan.csv  — course-level plan from the HLID Student Journey

Reads data/raw/planning/{UNI}-{hlid,prod}.xlsx (gitignored; see data/README.md).

KNOWN LIMITATION, by design: the Prod Sequence sheets have sparsely-filled
Unit ID columns. Coverage of delivered units varies (MRV ~82%, SGU ~65%,
Yenepoya/CDU ~40%). Low coverage means an incomplete export, NOT that content
was improvised. Callers must not read absence here as "never planned".

Usage: python scripts/build_designed.py
"""
import csv, os, re, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsx_dump import shared_strings, sheet_map, read_sheet  # stdlib xlsx reader already in repo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAW = "data/raw/planning"
OUT = "data/canonical/planning/designed"
os.makedirs(OUT, exist_ok=True)
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
UNIS = ["MRV", "Yenepoya", "SGU", "CDU", "ADYPU", "ANNA", "SVYASA", "NRI", "NSRIT",
        "CHALAPATHY", "NIU", "CRESCENT", "TAKSHASHILA", "AMET", "VGU", "NIATCH"]

EPOCH = None  # serials converted via datetime below


def to_date(serial):
    """Excel serial -> ISO date string. Raw serials must never reach the agent."""
    import datetime as dt
    try:
        f = float(serial)
    except (TypeError, ValueError):
        return ""
    if not (30000 < f < 60000):      # guard: not a plausible date serial
        return ""
    return (dt.datetime(1899, 12, 30) + dt.timedelta(days=f)).strftime("%Y-%m-%d")


def to_f(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def is_wad_component(title):
    """The Web-App-Dev-1 breakdown rows are the only real sub-modules in this
    template. Blank weeks_required alone misfires (e.g. NSRIT's C Programming has
    blank weeks but is a standalone course), so a sub-module must also be one of
    these WAD component rows."""
    t = (title or "").lower()
    return "build your own" in t or "modern responsive web design" in t


def week_num(s):
    """'Week - 1' / 'Week 2' / '3' -> int, or None.

    Guarded to 1..60: several sheets have a 'Week' column holding a DATE, not a week
    number, and a bare regex happily returns 2025 (the year) — which then derives a
    planned_start in 2064. A semester has no week 2025.
    """
    m = re.search(r"(\d+)", str(s or ""))
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 60 else None


def pick_week_col(hdr, grid, hi, c_uid):
    """Choose the week column by validating VALUES, not by trusting the header name.

    Layouts disagree: Yenepoya/SGU/CDU have both 'Week Number' (the number) and 'Week'
    (a date); MRV has only 'Week' (the number). Matching the header text picks the date
    column for three of four universities. So: score every 'week'-ish column by how many
    of its values are plausible week numbers, and take the winner.
    """
    cands = [i for i, h in enumerate(hdr) if "week" in (h or "").lower()]
    if not cands:
        cands = [i for i, h in enumerate(hdr) if "day" in (h or "").lower()]
    best, best_hits = None, 0
    for i in cands:
        hits = 0
        for r in range(hi + 1, min(hi + 400, len(grid))):
            row = grid[r]
            if c_uid is None or len(row) <= c_uid or not UUID.match((row[c_uid] or "").strip()):
                continue
            if len(row) > i and week_num(row[i]) is not None:
                hits += 1
        if hits > best_hits:
            best, best_hits = i, hits
    return best


def sheets_of(path):
    z = zipfile.ZipFile(path)
    sst = shared_strings(z)
    return [(name, read_sheet(z, p, sst)) for name, p in sheet_map(z)]


def find_col(hdr, *variants):
    for i, h in enumerate(hdr):
        hl = (h or "").lower()
        for tokens in variants:
            if all(t in hl for t in tokens):
                return i
    return None


def extract_prod(uni, path):
    """Unit-level designed sequence.

    A sheet qualifies only if its header has a unit-id column AND a week/day/start
    column — that selects the real per-course schedule sheets and naturally excludes
    the reference/scratch tabs (Gamma, Tech courses, rough, Updated Format), which
    carry unit ids but no schedule.
    """
    rows, used = [], []
    for name, grid in sheets_of(path):
        hdr = hi = None
        for r in range(min(20, len(grid))):
            row = grid[r]
            if find_col(row, ("unit", "id"), ("units", "id")) is not None and \
               find_col(row, ("week",), ("day",), ("start",)) is not None:
                hdr, hi = row, r
                break
        if hdr is None:
            continue
        c_uid = find_col(hdr, ("unit", "id"), ("units", "id"))
        c_crs = find_col(hdr, ("course",))
        c_top = find_col(hdr, ("topic",))
        c_ses = find_col(hdr, ("session", "name"))
        c_typ = find_col(hdr, ("type",))
        c_start = find_col(hdr, ("start",))
        c_week = pick_week_col(hdr, grid, hi, c_uid)
        n = 0
        for r in range(hi + 1, len(grid)):
            row = grid[r]
            cell = lambda i: row[i].strip() if (i is not None and len(row) > i and row[i]) else ""
            uid = cell(c_uid)
            if not UUID.match(uid):
                continue
            rows.append({
                "university": uni,
                "course": cell(c_crs) or name,
                "topic": cell(c_top),
                "unit_id": uid,
                "week": week_num(cell(c_week)),
                "planned_start": to_date(cell(c_start)),
                "session_name": cell(c_ses),
                "type": cell(c_typ),
                "sheet": name,
                "seq": r,
            })
            n += 1
        if n:
            used.append((name, n))
    return rows, used


def extract_hlid(uni, path):
    """Course-level plan from the 'High Level Student Journey' sheet, first block only.

    The sheet holds a Sem-1 block, then blanks, then a second (Sem-2) block under a
    repeated 'Course' header. We take the first block; Sem 2 has no matching designed
    sequence anyway.
    """
    target = None
    for name, grid in sheets_of(path):
        if "student journey" in name.lower():
            target = grid
            break
    if not target:
        return []
    hdr = target[0]
    c_sess = find_col(hdr, ("session", "count"), ("sessions", "count"))
    c_sh = find_col(hdr, ("session", "hour"))
    c_ph = find_col(hdr, ("practice", "hour"))
    c_mh = find_col(hdr, ("micro",))
    c_start = find_col(hdr, ("start",))
    c_end = find_col(hdr, ("end",))
    c_wk = find_col(hdr, ("week", "required"))
    out, blanks = [], 0
    for row in target[1:]:
        title = row[0].strip() if row and row[0] else ""
        if not title:
            blanks += 1
            if blanks >= 3:
                break
            continue
        if title.strip().lower() == "course":
            break  # second (Sem-2) block starts here
        cell = lambda i: row[i] if (i is not None and len(row) > i) else None
        weeks = to_f(cell(c_wk))
        out.append({
            "university": uni,
            "course": title,
            "sessions_count": to_f(cell(c_sess)),
            "session_hours": to_f(cell(c_sh)),
            "practice_hours": to_f(cell(c_ph)),
            "micro_assessment_hours": to_f(cell(c_mh)),
            "start_timeline": to_date(cell(c_start)),
            "end_timeline": to_date(cell(c_end)),
            "weeks_required": weeks,
            # A sub-module is a COMPONENT of the course above it, not a course. The HLID
            # lists e.g. Web Application Development-1 (75 sessions) and then its four
            # parts (28+15+17+15 = 75) as sibling rows. Summing every row double-counts
            # them — which overstated MRV's Sem-1 load as 593 hrs instead of 460 (+29%)
            # and turned a 93%-utilised plan into a fictional 120% overload.
            # A WAD-1 component row is always a sub-module (some HLIDs fill its weeks
            # cell, some don't) — keying off the component name, not the blank cell,
            # avoids both double-counting the parts and dropping real courses.
            "is_submodule": is_wad_component(title),
        })
    return out


seq_rows, plan_rows = [], []
for uni in UNIS:
    prod_path, hlid_path = f"{RAW}/{uni}-prod.xlsx", f"{RAW}/{uni}-hlid.xlsx"
    # some universities supply only the HLID (course-level plan), no unit-level Prod Sequence
    prod, used = extract_prod(uni, prod_path) if os.path.exists(prod_path) else ([], [])
    plan = extract_hlid(uni, hlid_path) if os.path.exists(hlid_path) else []
    seq_rows += prod
    plan_rows += plan
    dated = sum(1 for r in prod if r["planned_start"])
    print(f"  {uni:9s} sequence={len(prod):5d} units ({dated} with planned dates, {len(used)} sheets)  plan={len(plan)} courses")

# Derive planned_start where the sheet lacked a Start column: HLID semester start + (week-1)*7.
# Only MRV's sheets carry explicit dates; without this the other three have no timing at all.
import datetime as dt
hlid_start = {}
for p in plan_rows:
    if p["start_timeline"] and p["university"] not in hlid_start:
        hlid_start[p["university"]] = p["start_timeline"]
derived = 0
for r in seq_rows:
    if not r["planned_start"] and r["week"] and r["university"] in hlid_start:
        base = dt.datetime.strptime(hlid_start[r["university"]], "%Y-%m-%d")
        r["planned_start"] = (base + dt.timedelta(days=(r["week"] - 1) * 7)).strftime("%Y-%m-%d")
        r["planned_start_derived"] = True
        derived += 1
for r in seq_rows:
    r.setdefault("planned_start_derived", False)
print(f"  derived planned_start for {derived} units (week + HLID semester start)")

def write(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  {os.path.basename(path)}: {len(rows)} rows")

write(f"{OUT}/designed_sequence.csv", seq_rows,
      ["university", "course", "topic", "unit_id", "week", "planned_start",
       "planned_start_derived", "session_name", "type", "sheet", "seq"])
write(f"{OUT}/designed_course_plan.csv", plan_rows,
      ["university", "course", "sessions_count", "session_hours", "practice_hours",
       "micro_assessment_hours", "start_timeline", "end_timeline", "weeks_required",
       "is_submodule"])

# Report the parent/sub-module split and verify sub-modules really do roll up into a
# parent — if they don't, the is_submodule marker is wrong and totals will be off.
for uni in UNIS:
    rows = [p for p in plan_rows if p["university"] == uni]
    subs = [p for p in rows if p["is_submodule"]]
    tops = [p for p in rows if not p["is_submodule"]]
    hrs = lambda rs: sum((p["session_hours"] or 0) + (p["practice_hours"] or 0)
                         + (p["micro_assessment_hours"] or 0) for p in rs)
    if subs:
        sub_sess = sum(p["sessions_count"] or 0 for p in subs)
        match = [p["course"] for p in tops if (p["sessions_count"] or 0) == sub_sess]
        print(f"  {uni:9s} {len(tops)} courses ({hrs(tops):.0f} hrs) + {len(subs)} sub-modules "
              f"({sub_sess:.0f} sessions -> rolls up into: {match or 'NO PARENT MATCH — CHECK'})")
    else:
        print(f"  {uni:9s} {len(tops)} courses ({hrs(tops):.0f} hrs), no sub-modules")

assert seq_rows, "no designed sequence extracted — check data/raw/planning/*.xlsx"
assert all(r["planned_start"] == "" or re.match(r"^\d{4}-\d{2}-\d{2}$", r["planned_start"])
           for r in seq_rows), "planned_start must be ISO date or empty, never a raw serial"

# planned_start must land inside the academic year. A 'Week' column holding a date once
# derived planned_start=2064 and nothing caught it until the drift came out at -14,125 days.
out_of_range = [r for r in seq_rows if r["planned_start"] and not ("2025-01-01" <= r["planned_start"] <= "2026-12-31")]
assert not out_of_range, (
    f"{len(out_of_range)} units have planned_start outside 2025-2026 "
    f"(e.g. {out_of_range[0]['university']}/{out_of_range[0]['sheet']} -> {out_of_range[0]['planned_start']}). "
    "The week column is probably a date, not a week number.")

