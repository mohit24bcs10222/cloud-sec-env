# Hackathon Tasks — Cloud Sec Env

> 48-hour tracking doc. Team of 2 (Person A = Env track, Person B = Training/Agent track). Tick as you go.

## Legend
- **Duration** = estimated hours for that step
- **Hours** = when it runs in the 48h window (H0 = clock start)
- **Done when** = objective completion criterion

---

## Pre-work (before H=0, ~3-4h per person — do independently)

| # | Task | Owner | Duration | Done when | ✓ |
|---|---|---|---|---|---|
| 1 | OpenEnv docs + scenario + accounts | Both | 1.5h | Read README, walked 1 example env, HF+Colab accounts + tokens ready | ☐ |
| 2 | Observability primer | Person A | 0.5h | Can explain logs/metrics/traces + trace_id coherence from memory | ☐ |
| 3 | Unsloth LoRA tutorial + toy Colab run | Person B | 1.5h | Ran Unsloth's official Qwen2.5 SFT notebook once, loss decreased | ☐ |

---

## P0 — Align (H0-3, 3h together)

| # | Task | Owner | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|---|
| 4a | Lock 6 data schemas (log, span, metric, ticket, slack, KB) | Both | 1h | 0-1 | Schema doc committed to repo | ☐ |
| 4b | Lock 6 tool signatures | Both | 0.5h | 1-1.5 | Tool API contract doc committed | ☐ |
| 4c | Scaffold repo + hello-world OpenEnv env running locally | Both | 1.5h | 1.5-3 | `env.reset()` returns a response over HTTP | ☐ |

---

## P1 — Parallel Build (H3-12, 9h each track)

### Person A — Environment

| # | Task | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|
| 5a | Hand-author logs (~200 lines, OIDC key scenario) | 1.5h | 3-4.5 | `logs.jsonl` exists, trace_ids consistent | ☐ |
| 5b | Hand-author traces (~20 span trees) | 1h | 4.5-5.5 | `traces.json` matches logs | ☐ |
| 5c | Hand-author metrics (small time series) | 0.5h | 5.5-6 | `metrics.csv` exists | ☐ |
| 5d | Hand-author tickets (8, incl. the change ticket) | 0.5h | 6-6.5 | `tickets.yaml` incl. CHG-xxxx | ☐ |
| 5e | Hand-author slack (~20 msgs across channels) | 0.5h | 6.5-7 | `slack.yaml` exists, timestamps align | ☐ |
| 5f | Hand-author KB (6 docs, 1 stale + 1 correct-buried) | 1h | 7-8 | 6 markdown files in `kb/` | ☐ |
| 6 | Implement 6 tool endpoints (FastAPI + DuckDB/SQLite) | 3h | 8-11 | All 6 tools return data over HTTP | ☐ |
| 7 | Wire into OpenEnv HTTP (reset + step) | 1h | 11-12 | Manual curl reset+step works | ☐ |

### Person B — Training/Agent

| # | Task | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|
| 8 | **🚨 Hello-world LoRA fine-tune (HARD GATE)** | 3h | 3-6 | Loss decreased, adapter saved. **STOP if broken at H=6** | ☐ |
| 9 | Agent rollout harness (against mocked env) | 3h | 6-9 | Script takes (model, task) → trajectory log | ☐ |
| 10 | Reward scorer (step-level + terminal) | 3h | 9-12 | Scores a mocked trajectory correctly | ☐ |

---

## P3 — Integrate (H12-14, 2h together)

| # | Task | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|
| 11 | Point harness at real env, first live Opus rollout | 2h | 12-14 | Opus produces a full trajectory; reward printed | ☐ |

---

## P4 — Calibrate (H14-18, 4h together)

| # | Task | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|
| 12 | Iterate data/tools/scorer until Opus solves reliably | 4h | 14-18 | Opus Pass@1 measured, target 40-60% | ☐ |

---

## P5 — Harvest training data (H18-24, 6h)

| # | Task | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|
| 13 | Run 30-50 Opus rollouts at temp 0.7, keep passing ones | 6h | 18-24 | 100-200 step-level SFT examples saved. **Can run overnight — mostly API waits** | ☐ |

---

## P6 — Baseline (H24-28, 4h)

| # | Task | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|
| 14 | Qwen2.5 baseline rollouts + sub-task metrics | 4h | 24-28 | Baseline pass rate + sub-metrics recorded | ☐ |

---

## P7 — Fine-tune (H28-36, 8h — pad generously)

| # | Task | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|
| 15 | SFT fine-tune Qwen on harvested data | 8h | 28-36 | Adapter saved, training loss decreased. If flat, pivot to narrower metric | ☐ |

---

## P8 — Proof (H36-40, 4h together)

| # | Task | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|
| 16 | Fine-tuned Qwen rollouts + before/after + reward curve | 4h | 36-40 | Side-by-side trajectories captured, reward curve plotted | ☐ |

---

## P9 — Story assets (H40-44, 4h — parallelized across both)

| # | Task | Owner | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|---|
| 17 | Reward curve + trajectory comparison visuals | Person B | 1.5h | 40-41.5 | PNGs ready for demo | ☐ |
| 18 | Record 2-min demo video | Person A | 2h | 40-42 | Unlisted YouTube link ready | ☐ |
| 19 | Write HF blog post | Person A | 2h | 42-44 | Draft published | ☐ |
| 20 | Deploy env to HF Spaces | Person B | 1.5h | 41.5-43 | Public Space URL works from fresh machine | ☐ |
| 21 | Publish Colab training notebook | Person B | 1h | 43-44 | Notebook runs end-to-end on "Run all" | ☐ |

---

## P10 — Buffer (H44-48, 4h)

| # | Task | Owner | Duration | Hours | Done when | ✓ |
|---|---|---|---|---|---|---|
| 22 | Final debug, polish, submit all links | Both | 4h | 44-48 | Submission form filled, links verified | ☐ |

---

## Critical path + parallelism summary

**Critical path (single chain, must stay on schedule):**
Pre-work → P0 align → P1 Person B Task #8 (gate at H=6) → P3 integrate → P4 calibrate → P5 harvest → P6 baseline → P7 fine-tune → P8 proof → P9 assets → P10 submit

**Fully parallel (shouldn't block each other):**
- P1 Person A track (5a-7) vs. Person B track (8-10)
- P9 story assets (17-21)

**Hard gates — if these fail, replan immediately:**
- **H=6:** Task #8 hello-world fine-tune must pass
- **H=14:** Opus must be producing non-broken trajectories
- **H=28:** Training data must be harvested in SFT-ready format
- **H=36:** Fine-tune must show loss decrease (if flat, pivot to narrower metric)

---

## Time-risk ranking

Where slippage is most likely — compress elsewhere if hit:

1. **P7 fine-tune (8h)** — pad is already in, don't let it spill into P8
2. **P4 calibrate (4h)** — if Opus is wildly off, can extend by stealing from P5
3. **P1 data authoring (5h)** — resist over-polishing; 80% coherent is fine

---

## Key architectural calls (locked)

- Task #1 scenario: **OIDC signing-key rotation** (admin rotated key in cloud-1/3, forgot cloud-2)
- Training approach: **SFT on Opus trajectories** (not RL)
- Target model: **Qwen2.5-1.5B or 3B** (not 8B)
- Env style: **frozen snapshot** (not live/dynamic)
- Scope: **1 flagship task only** (no second task, no matter how tempting)
- Tools: **6** (logs_search, trace_get, metric_query, ticket_search, slack_search, kb_search)

---

## Submission checklist (hackathon requirements)

- ☐ OpenEnv-compliant environment
- ☐ Env hosted on HuggingFace Spaces
- ☐ Minimal training script in Colab (Unsloth or TRL)
- ☐ Mini-blog on HuggingFace OR mini-video on YouTube <2 min (we're doing both)
- ☐ Reward curve / before-after evidence of training improvement
