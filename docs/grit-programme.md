# GRIT 2026–27 — programme knowledge (reference context)

Served via `guide()` alongside the academic-delivery notes. A **second product** the copilot must
know: **G.R.I.T — Global Readiness Immersion Trip**, NIAT/NxtWave's year-long gamified skill
competition whose top performers win a fully sponsored international trip.

**GRIT is reference context, NOT queryable data.** There are **no GRIT tables** in the DuckDB store —
do not `run_sql` against it. Answer GRIT questions from THIS document. The delivery/planning data
(`delivered_*`, `course_plan_vs_actual`, …) is a different product (NIAT university delivery) and
never mixes with GRIT numbers.

**Sources.** Updated from the **"GRIT Program Briefer (2026-27)"** (16 Jul — the official *How GRIT
works* explainer) over the earlier Master Knowledge Document. **Where they differ the briefer is newer
and wins**; superseded values are flagged in §14. Dates, destinations, seat splits, salary bands, and
Miles values are **indicative/internal, subject to change**.

---

## 1. What GRIT is
**G.R.I.T = Global Readiness Immersion Trip.** A year-long, gamified skill competition run exclusively
for NIAT students (batches 2023/24/25) across partner campuses. Students earn **Miles** by competing
in contests, clearing skill levels, unlocking track badges, and completing verified external
achievements. Miles + badges set leaderboard rank; the top performers win a **fully sponsored
international trip** to a global tech hub. Contests **Feb 2026 → Feb 2027**; travel **May–Jul 2027**
(tentative). Framing: *"start early, win early"* — skill up from Year 1, not at final-year placement pressure.

## 2. Snapshot & key facts
| Attribute | Detail |
|---|---|
| Name | G.R.I.T — Global Readiness Immersion **Trip** 2026-27 |
| Run by | NIAT / NxtWave |
| Eligible batches | 2023, 2024, 2025 |
| Contest window | Feb 2026 → Feb 2027 |
| Travel | May–Jul 2027 (tentative) |
| Prize | Fully sponsored trip — airfare, food, accommodation, local travel — to a global hub (US, China, Japan, Germany, Singapore, South Korea…). Student pays **passport & visa** ("skin in the game"). One immersion per student. |
| Eligibility | ≥75% attendance from 15 Feb 2026 · on-time semester registration · NIAT code of conduct · batches 2023/24/25 |
| Qualify | Earn **≥1 track badge by December 2026** + clear the final interview round |
| Public site | grit.niatindia.com · support niat.grit@nxtwave.tech |
| Seats (master doc — briefer silent) | 1,000 announced; split **2 : 132 : 866** (2023:2024:2025). Indicative; the 16 Jul briefer does not restate seat counts. |

## 3. Glossary — use these terms precisely
- **Miles** — the score; earned via contests + verified achievements. More Miles = higher rank + higher reward chance.
- **Tracks** — curated skill bundles leading to a certification: AI Product Mastery, AI Systems Mastery, AI Models Mastery, AI Robotics Mastery (more coming).
- **Skills** — what a student practices (e.g. Applied Gen AI Development, CS Fundamentals, UI Engineering, DS & ML).
- **Skill Levels L1–L4** — difficulty inside a skill; higher = more Miles.
- **Track Badge** — the certification within a track. Progression **Novice → Specialist → Expert → Elite → Legend** (informally "Novice up to Grand Master"). Each needs a defined skill+level set + a **Level Clearance Interview**.
- **Medals** — Gold / Silver / Try Again per contest attempt → maps to Miles.
- **GRIT Contests** — proctored contests (run via SEB) where levels are cleared.
- **Level Clearance Interview** — verification step ("a quick layover") before Miles/badges are awarded.
- **Leaderboards** — Miles + badges decide the trip. Two tiers: **Pre-Qualiflyers** (all eligible/registered/approved) · **Qualiflyers** (≥1 Track Badge completed).
- **Ticket to Finale** — direct finale path via a standout external achievement (bypasses the grind).
- **Bonus Miles** — Miles from verified external platforms/competitions.
- **SEB** — Secure Exam Browser (proctoring). **SPOCs** — campus single points of contact. **GRIT Dashboard** — the product running Miles/leaderboard/eligibility/Bonus-Miles verification (built on Replit).

## 4. Student roadmap
Choose a **Track** → pick a **Skill** → enter **GRIT Contests** → clear **Skill Levels (L1–L4)** →
score **Miles** (by medal) → crack the **Level Clearance Interview** → unlock a **Track Badge** →
climb the **Leaderboard** → top students win the trip. A Track contains multiple Badges; each Badge is
a defined combination of Skills at defined Levels + an interview.

## 5. The three ways to win  *(replaces the old "Lucky Draw")*
1. **Top the GRIT Leaderboard** — max Miles, unlock Track Badges, top the **Qualiflyer** leaderboard.
2. **Direct Ticket to Finale** — a standout external achievement, bypassing the grind, in one of:
   Competitive Programming (e.g. ACM-ICPC Regionals) · Open Source (e.g. GSoC 2026/27) ·
   Entrepreneurship (reputed accelerator/incubator, or equity funding/grants from a recognised
   VC/angel/family office) · Research & Academia · Content Creation. (More opportunities added over time.)
3. **Surprises & rewards** — hitting qualifying milestones raises the chance of goodies/exclusive rewards throughout.

## 6. Leaderboards & ranking
Two tiers — **Pre-Qualiflyers** (all eligible) and **Qualiflyers** (≥1 badge). Ranking priority:
1. **Total Miles** → 2. **highest Track Badge level** (Legend > Elite > Expert > Specialist > Novice)
→ 3. **skill-level depth** (L4 > L3 > L2 > L1) → 4. **earliest timestamp** (first to the milestone).
*(Internal: leaderboard / Miles-math accuracy is a real operational risk — trip eligibility depends on it.)*

## 7. The Miles economy
Loop: **GRIT contests → clear skill levels → score Miles (by medal) → unlock track badges → climb the
leaderboard**; verified external achievements add Bonus Miles (§11).

**Medals** (each skill-level attempt returns one):

| Outcome | Meaning | Miles | Unlocks next level? |
|---|---|---|---|
| Gold | Top band | Full Miles for the level | Yes |
| Silver | Strong/partial pass | ~90% of Gold | Yes |
| Try Again | Below threshold | Flat **5** (participation) | No — must re-attempt to ≥ Silver |

**Attempt rules:** unlimited attempts via later contests · only the **highest** score counts · a level
unlocks only after Gold/Silver on the previous one · **≥5-day gap** between re-attempts of the same level.

**Miles per level by weight** (Gold shown; Silver ≈ 90%, Try Again = 5):

| Level weight | Gold |
|---|---|
| Light (L1 basic) | 10 |
| Standard — L1 flagship / L2 basic | 20 / 40 |
| Advanced — L2 flagship / L3 | 80 / 200 |
| Elite (L4) | 400 |

> Exact Mile values per level & medal live in the internal skill-level and badge tables. Superseded: an
> earlier model used **Grade A / B / RA** with per-skill multipliers; current model is Gold / Silver / Try-Again.

## 8. Skills & Levels catalogue

Gold Miles per level. "Locked" levels open progressively.

| Skill | L1 | L2 | L3 | L4 | Topics (by level) |
|---|---|---|---|---|---|
| Computational Thinking | 20 | 80 | 200 | 400 | L1 arrays/strings, loops, basic math, simulation, time-complexity · L2 binary search, hashing, sliding window, stacks/queues, prefix sum · L3 greedy, graphs, BFS/DFS, basic DP, backtracking, heap · L4 advanced DP/graphs, segment trees, shortest-path |
| Applied Gen AI Development | 20 | 80 | 200 | 400 | L1 prompt engineering, zero/few-shot, output validation · L2 API integration, RAG basics, embeddings · L3 vector DBs, prompt chaining, guardrails · L4 fine-tuning, multi-agent workflows, cost optimisation |
| UI Engineering | 10 | 40 | — | — | L1 semantic HTML, CSS box model, flexbox, JS/DOM · L2 API integration, state, async JS, error handling |
| Server-Side Engineering | 10 | 40 | — | — | L1 REST, routing, middleware, auth basics · L2 JWT auth, caching, rate limiting, transactions |
| SQL | 10 | 40 | — | — | L1 SELECT/WHERE/GROUP BY/JOIN/subqueries · L2 indexing, window functions, normalization, transactions |
| CS Fundamentals | 10 | 40 | — | — | L1 OS/DBMS/networking basics, OOPS · L2 OS scheduling, indexing internals, transactions, memory mgmt |
| System Design | 20 | 80 | — | — | L1 HLD, DB schema, APIs, monolith vs microservices · L2 caching, load balancing, sharding, message queues |
| Quantitative Reasoning | 10 | 40 | — | — | L1 percentages, ratios, averages, P&L, SI/CI, time&work, speed–distance, number systems · L2 P&C, probability, DI, puzzles |
| Critical Thinking & Communication | 10 | 20 | 40 🔒 | — | L1 grammar/tenses/prepositions, sentence correction, RC basics · L2 para jumbles, critical reasoning, inference RC · L3 Locked |
| DS & ML | 20 | 80 | 200 🔒 | 400 🔒 | L1 Python for DS (NumPy/Pandas/EDA), stats, supervised ML, model eval · L2 inferential stats, feature eng, ensembles, unsupervised, tuning · L3/L4 Locked |
| Data Intelligence | 10 | 40 | — | — | L1 analytics workflow, data cleaning, Power BI/Tableau/Excel, descriptive · L2 advanced viz, data modeling (star schema), DAX, storytelling |
| Physical AI | 20 | 80 | 200 🔒 | 400 🔒 | L1 Linux/ROS2, robot modelling/maths, Gazebo, SLAM, nav, CV, embedded · L2 advanced ROS2, ros2_control, MoveIt2, path planning, sensor fusion · L3/L4 Locked |
| Human Skills for the AI Era | 10 🔒 | 40 🔒 | — | — | Locked |
| Quantitative Finance Foundation | 20 🔒 | 80 🔒 | 200 🔒 | — | Locked |

## 9. Contest formats & score bands

Pattern · duration · band → medal (Gold / Silver / Try-Again). Syllabus + sample questions live in
the Assessments workbook (not reproduced — they change as the question bank evolves).

| Skill · Lvl | Pattern | Duration | Gold / Silver / Try-Again |
|---|---|---|---|
| Computational Thinking L1 | Coding | 90 min | 100 / 83.33–99.99 / 0–83.32 |
| Computational Thinking L2 | Coding | 90 min | 100 / 75–99.99 / 0–74.99 |
| UI Engineering L1 | MCQs + Coding | 90 min | 85–100 / 70–84.99 / 0–69.99 |
| UI Engineering L2 | MCQs + IDE Coding | 90 min | 90–100 / 80–89.99 / <80 |
| CS Fundamentals L1 | MCQs | 40 min | 90–100 / 85–89.99 / 0–84.99 |
| CS Fundamentals L2 | MCQs | 60 min | 90–100 / 85–89.99 / 0–84.99 |
| Applied Gen AI L1 | MCQs | 45 min | 90–100 / 80–89.99 / 0–79.99 |
| Applied Gen AI L2 | MCQs | 45 min | 90–100 / 80–89.99 / 0–79.99 |
| Critical Thinking & Comm. L1 | MCQs | 40 min | 95–100 / 75–94.99 / 0–74.99 |
| Critical Thinking & Comm. L2 | MCQ | 30 min | 90–100 / 80–89.99 / <80 |
| Server-Side Engineering L1 | MCQs + Coding | 90 min | 95–100 / 90–94.99 / 0–89.99 |
| Server-Side Engineering L2 | MCQs + Coding | **TBU** | Will be updated shortly |
| Quantitative Reasoning L1 | MCQs | 30 min | 90–100 / 75–89.99 / 0–74.99 |
| Quantitative Reasoning L2 | MCQ | 40 min | 95–100 / 80–94.99 / 0–79.99 |
| SQL L1 | MCQs + Coding | 90 min | 90–100 / 85–89.99 / 0–84.99 |
| SQL L2 | MCQs + Coding | 90 min | 90–100 / 80–89.99 / 0–79.99 |
| DS & ML L1 | MCQs + Coding | 90 min | 90–100 / 85–89.99 / 0–84.99 |
| Physical AI L1 | MCQs + Coding | 90 min | 85–100 / 70–84.99 / 0–69.99 |

## 10. Certifications — tracks & badges
A **Track Badge** is earned by clearing a defined skill+level combination **plus a Level Clearance
Interview**. Badges are **sequential (no skipping)**: **Novice → Specialist → Expert → Elite → Legend**.

**Tracks:** AI Product Mastery · AI Systems Mastery · AI Models Mastery · AI Robotics Mastery (more TBA).
(AI Models & AI Robotics badge matrices still being finalised.)

**Badge → indicative salary band (master doc; internal):** Novice 3.5–6 · Specialist 6–12 ·
Expert 12–18 · **Elite** 18–25 · **Legend** 25+ LPA.

**Track composition (skill levels per badge):**
- *AI Product Mastery* — **Novice**: Computational Thinking L1, CS Fundamentals L1, Applied Gen AI L1, UI Engineering L2. **Specialist**: CT L2, CS Fund L1, Gen AI L2, UI Eng L2, Server-Side Engineering L1, SQL L1. **Expert**: + System Design L1. Elite / Legend: TBD.
- *AI Systems Mastery* — **Novice**: CT L1, CS L1, GenAI L1, Quant Reasoning L1, Critical Thinking L2 · **Specialist**: CT L2, CS L1, GenAI L2, Quant L1, CritThink L2 · **Expert**: CT L3, CS L2, GenAI L3, System Design L1, Quant L1, CritThink L2 · **Elite**: CT L4, CS L2, GenAI L4, Quant L1, CritThink L2 · Legend: TBD.

Expert / Elite / Legend badges are **Locked**, unlocked progressively.

## 11. Bonus Miles — external achievements (verified)
Beyond contests, eligible students earn Bonus Miles by proving skills on recognised external
platforms; achievements are **verified** (e.g. CP ratings via an offline proctored test).
- **Competitive programming** — indicative **Codeforces**: Newbie (<1200, ≥2 problems attempted) **20** · Pupil (≥1200) **80** · Specialist (≥1400) **200** · Expert (≥1600) **400** · Candidate Master (≥1900) **higher**. Also CodeChef and LeetCode rating milestones.
- **Physical AI & Robotics** — national competitions like **Smart India Hackathon (SIH)** and **VBYLD (Design for Bharat)**; finalists/winners score significantly.
- **Hackathons & more** — recognised national/international hackathons across AI, tech, engineering.

*A Bonus-Miles framework for external co-curricular achievements (stipend internships, paid freelancing,
hackathon wins) is being aligned with the Student Success and Assessment/Outcomes heads before finalisation.*

## 12. Operational & product context (internal)
- **GRIT Dashboard** — built on **Replit**; owns Miles calculation, leaderboard ranking, contest eligibility, and Bonus-Miles verification. *It lives OUTSIDE the learning portal — integration talks should be clear about which system owns which calculation.*
- **Contest ops** — run across campuses via **SEB (Secure Exam Browser)**; a WhatsApp ops group handles real-time escalations. Recurring issues: access/provisioning failures, SEB stability/security, coding-environment defects.
- **Malpractice** — IP-anomaly + SEB malicious-pattern flags, auto-flagging, invigilator incentives, a student appeal process, and post-contest risk-scoring.
- **GRIT Awards** — campus-level Student-of-the-Year + centrally administered category awards (single self-nomination form).
- **Coordination** — campus **SPOCs**; scoped to batches 2023/24/25. Roadmap: Dashboard product hire, GRIT Awards execution, a student-dashboard Milestones tab, and finalising the Bonus-Miles framework.

## 13. Companion programmes (context)
GRIT sits in a wider NIAT ecosystem: **MINT** (Monetise Intelligence and Talent — earn per project on
real business problems · mint.niatindia.com) · **BRAVE** (Boosting Revenue through AI Value Engineering
— teams build AI solutions for SMB clients and generate revenue · brave.niatindia.com) · **SPARK**
(creator programme — win by crossing follower/revenue thresholds).

## 14. Known changes & open items (flag these — don't state one side as settled)
- **"Lucky Draw" is superseded.** The 16 Jul briefer replaces the old "Top-of-Leaderboard + Lucky Draw"
  seats model with the **three ways to win** (leaderboard / Ticket to Finale / surprises) and the
  **Pre-Qualiflyers / Qualiflyers** tiers. Don't cite Lucky Draw as current.
- **Badge names changed** — Novice → Specialist → Expert → **Elite → Legend** (was …Master → Grand
  Master). "Grand Master" is the old/informal label.
- **Seat split (2 / 132 / 866; 1,000 seats)** — from the master doc; the briefer doesn't restate it.
  (Workbooks also cited 10:988:6502 and a 500/500 split — superseded.) Treat as indicative.
- **Salary bands** (Novice 3.5–6 … Legend 25+) — master-doc internal figures, mapped to the new badge
  names. Placement benchmark: "entry-level tech roles" / "3.5 LPA" — internal, not a published promise.
- **Locked / TBD** — Server-Side L2 duration TBU; several Locked levels; AI Models & AI Robotics badge
  matrices unfinished; Elite/Legend rows TBD in the defined tracks.
