"""Build the committed Student Performance canonical CSV from the raw export.

Raw (gitignored, data/raw/performance/) -> canonical (committed,
data/canonical/performance/). Two jobs:
  1. Add `institute_name` -- the model's ONLY institute join key -- via a curated
     crosswalk. The raw file labels colleges differently (spelling/case/suffix), and
     nothing in the store fuzzy-matches institutes, so this map is the load-bearing link.
     We map TO the model's existing institute_name spelling even where the raw looks more
     correct (Yenepoya/Takshashila/Ghodawat) -- renaming canonical colleges would break
     every existing join, so that's out of scope here.
  2. snake_case the 24 headers and normalise whitespace on the key/dimension columns so
     the table links on institute_name + semester + section.

The rows have NO course/date column, so the raw grain is un-keyed (many rows per
section). Aggregation + rate recompute happens in the load_duckdb.py views, not here.
Mirrors scripts/build_operational.py (raw -> canonical transform).

Run: python scripts/build_student_performance.py
"""
import csv
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "performance", "student_performance_raw.csv")
OUT = os.path.join(ROOT, "data", "canonical", "performance", "student_performance.csv")

# raw `University` -> canonical `institute_name` (must equal universities.institute_name).
INSTITUTE = {
    "A Dy Patil University":               "A Dy Patil University",
    "AMET (Academy of Maritime Education)": "AMET",
    "Annamacharya University":             "Annamacharya University",
    "CDU (Chaitanya Deemed University)":   "Chaitanya Deemed-to-be University",
    "Chalapathi Institute of Technology":  "Chalapathy (CITY)",
    "Crescent University":                 "Crescent University",
    "MRV University":                      "Malla Reddy Vishwavidyapeeth",
    "NRI Institute of Technology":         "NRI",
    "NSRIT":                               "NSRIT University",
    "Noida International University":       "Noida International University",
    "S-Vyasa University":                  "S-VYASA",
    "Sanjay Godhawat University":          "Sanjay Ghodawat University",
    "Takshashila University":              "Takshasila University",
    "Vivekananda Global University":       "Vivekananda global University",
    "Yenepoya University":                 "Yenapoya University",
}

# raw header -> snake_case column (order preserved for the output).
# Two-level hierarchy: `subject` (the name — 22 values) is the human label; a subject can
# span several `course_id`s (27 values), the precise NxtWave course UUID (dash-less 32-hex).
# `Course Name` is dropped (it equals `Subject` in every row). `course_id` resolves to
# subject_tags.course_id / courses.course_ids for ~60% of courses (see data-notes).
COLS = {
    "University": "university",
    "Semester": "semester",
    "Subject": "subject",
    "Course ID": "course_id",
    "Batch": "batch",
    "Section": "section",
    "Number of Sections": "num_sections",
    "Students (Section-wise)": "students",
    "Scheduled MCQ Practices": "scheduled_mcq_practices",
    "MCQ Practice Attendance": "mcq_attendance",
    "MCQ Attendance %": "mcq_attendance_pct",
    "Total MCQ Questions": "total_mcq_questions",
    "MCQ Question Attempts": "mcq_attempts",
    "MCQ Expected Attempts": "mcq_expected_attempts",
    "MCQ Attempt %": "mcq_attempt_pct",
    "MCQ Correct Answers": "mcq_correct",
    "MCQ Accuracy %": "mcq_accuracy_pct",
    "Scheduled Coding Practices": "scheduled_coding_practices",
    "Coding Practice Attendance": "coding_attendance",
    "Coding Attendance %": "coding_attendance_pct",
    "Total Coding Problems": "total_coding_problems",
    "Coding Question Attempts": "coding_attempts",
    "Coding Expected Attempts": "coding_expected_attempts",
    "Coding Attempt %": "coding_attempt_pct",
    "Coding Question Completions": "coding_completions",
    "Coding Completion %": "coding_completion_pct",
}

WS_COLS = {"university", "semester", "subject", "batch", "section"}  # collapse odd whitespace on keys


def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def main():
    with open(RAW, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    unknown = sorted({r["University"] for r in rows if r["University"] not in INSTITUTE})
    if unknown:
        raise SystemExit(f"Unmapped universities (add to INSTITUTE crosswalk): {unknown}")

    out_cols = ["institute_name"] + list(COLS.values())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_cols)
        w.writeheader()
        for r in rows:
            rec = {"institute_name": INSTITUTE[r["University"]]}
            for raw_k, out_k in COLS.items():
                v = r[raw_k]
                rec[out_k] = norm_ws(v) if out_k in WS_COLS else v
            w.writerow(rec)

    print(f"wrote {len(rows)} rows -> {OUT}")
    print(f"{len(set(INSTITUTE.values()))} institutes: {sorted(set(INSTITUTE.values()))}")


if __name__ == "__main__":
    main()
