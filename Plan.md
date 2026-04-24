# Cloud Sec Env — Implementation Plan

> **Companion to:** `Environment_Spec.md` (the problem statement).
> **Author context:** solo developer, full-stack background, first time working with observability / LLM-agent evaluation / cloud security. Plan is written to be shared with a collaborator who wasn't in the design discussion.

---

## 1. What we're building (one paragraph)

A simulated "mini-company" that an LLM agent investigates. The agent is handed an alert or incident ticket, uses tools to query logs, traces, metrics, tickets, chat messages, and a knowledge base, and proposes a fix. We score how well different LLMs (Qwen3-8B vs. Opus, etc.) solve 10 hand-crafted incidents. The environment is meant to be realistic enough that a frontier model passes <50% of tasks, and a small model fails almost all of them.

**Target framework:** Meta's **OpenEnv** — the open-source standard for pluggable LLM agent environments (HTTP-based, gymnasium-inspired `reset`/`step` API, containerized).

---

## 2. Mental model

Break the problem into 6 elementary pieces:

| # | Piece | Full-stack analogue |
|---|---|---|
| 1 | Simulated world — services running in `cloud-1/2/3`, users, admins, normal behavior | Seeded dev DB with fake orgs/users |
| 2 | Telemetry streams — logs, metrics, traces emitted by those services | App logs → ELK / DataDog-style store |
| 3 | Auxiliary stores — tickets, chat messages, KB docs | Postgres tables + search indexes |
| 4 | Tool interfaces — query APIs the agent calls | REST/RPC endpoints |
| 5 | Tasks (×10) — incident scenarios with ground truth + expected investigation path | E2E test cases |
| 6 | Eval harness — runs a model through a task, records trajectory, scores pass/fail | CI runner + test reporter |

The **spec's hardest quality bar** is that the telemetry must be *coherent but messy*: `trace_id`s match across logs and traces, service names are fuzzy (`auth-svc` vs. `auth_svc`), some logs missing request IDs — realistic real-world noise.

---

## 3. Architectural decisions (locked)

### 3.1 Data generation approach — hand-author first, simulator later

We will NOT start by building a data simulator. We will:

1. Hand-author the data for **Task #1 only** (a few hundred log lines, ~20 traces, ~8 tickets, ~20 Slack messages, ~5 KB docs — all typed directly as JSON/YAML files).
2. Build tools around it, wire into OpenEnv, run Opus end-to-end.
3. **Only then** design the simulator for generating the remaining 9 tasks at volume.

Rationale: you learn more from one working end-to-end task than from a week of simulator scaffolding against unclear requirements. Hand-authoring forces you to feel what "coherent" and "realistic" actually mean before writing code to generate it.

### 3.2 Live vs. snapshot environment → snapshot

Each task is served as a frozen "world state at incident time." The env does not evolve during agent investigation. ~5× less work than live simulation, fully deterministic evals. Nothing in the spec requires live behavior.

### 3.3 Tool surface → many-thin, product-shaped (~8-12 tools)

Each tool mirrors a real product idiom (DataDog-ish log search, Jira-ish ticket search, Slack-ish messaging, Confluence-ish KB search). Agents perform better with product-familiar APIs because they've seen those in training. Draft tool set:

- `logs_search(filters, time_range)`
- `trace_get(trace_id)`, `trace_search(filters)`
- `metric_query(name, time_range, labels)`
- `ticket_search(query)`, `ticket_get(id)`
- `slack_search(channel, query)`
- `kb_search(query)`, `kb_read(doc_id)`
- `list_deployments(cloud, time_range)`
- `list_services(cloud)`

### 3.4 Task authoring → top-down

Write the incident story first (company, customer, root cause, expected trajectory, success criteria), then construct data to manifest it. Later, once the simulator exists, bottom-up authoring also becomes viable.

### 3.5 Tech stack (recommended, not locked)

- **Python 3.11** — everything
- **DuckDB over parquet** — logs, traces, metrics (blazing analytical queries, no infra)
- **SQLite + FTS5** — tickets, KB, Slack (stdlib, full-text search)
- **FastAPI** — implementing the tool endpoints
- **OpenEnv** — the env wrapper (exposes tools as HTTP)
- **Anthropic + HF APIs** — eval harness rollouts (Opus, Qwen3-8B)

---

## 4. Task #1 — our concrete anchor

We've designed Task #1 in full as the vertical-slice target.

> **Hackathon update (2026-04-24):** Task #1's root cause was swapped from the original AWS IAM `aud`-claim / `StringEquals` variant to an **OIDC key-rotation** variant. Same investigative shape (scoping to the right cloud, correlating a change ticket, reading Slack, avoiding red herrings, separating signal from baseline noise) but dramatically easier to narrate in a 2-minute demo video. The original `aud`-claim design is preserved in git history.

### 4.1 Scenario (ground truth — agent does not see this)

- **Fictional company:** *NimbusGuard*, a cloud-security SaaS.
- **Customer:** *Acme Corp*, enterprise tier, authenticates via OIDC federation from their Okta tenant.
- **Topology:** 3 clouds (`cloud-1` us-east, `cloud-2` us-west, `cloud-3` eu-west). Services per cloud: `api-gateway`, `auth-svc`, `sts-broker`, `policy-svc`, `audit-logger`.

**Root cause:** At T-16h, SRE `j.patel` rotated the OIDC signing key via Terraform change `CHG-1891` as part of quarterly security hygiene. The apply landed cleanly on `cloud-1` and `cloud-3` but **silently failed on `cloud-2`** — a concurrent Terraform run by another engineer held the state lock, so the new public-key config never loaded into `cloud-2`'s `sts-broker`. The failure surfaced only as a warning in the Terraform output, not an error; `j.patel` didn't notice and declared victory.

**The bug:** Okta now signs Acme's JWTs with the NEW private key. `cloud-1` and `cloud-3` validate them correctly (they received the new public key). `cloud-2`'s `sts-broker` is still checking signatures against the OLD public key, so it rejects every Acme token with `signature verification failed`.

**Why only Acme is hammered:** Acme's primary routing is to `cloud-2` (geographic). Other tenants route to `cloud-1`/`cloud-3` and are unaffected. So the alert fires only on `cloud-2`'s `auth-svc`.

**Correct fix:** re-apply the Terraform for `cloud-2` to push the new public key into `sts-broker`. Do NOT roll back the rotation across the other clouds — they're healthy.

### 4.2 Agent's input (the alert)

```
ALERT  auth_svc_5xx_rate_cloud2
SEV-2  fired 2026-04-22 14:02 UTC
CONDITION  HTTP 5xx rate on auth-svc in cloud-2 > 5% for 30min
CURRENT    8.7%
RUNBOOK    kb://runbooks/auth-svc-5xx
```

### 4.3 Ideal agent trajectory (6-9 steps)

1. Parse alert → scope to `cloud-2`, service `auth-svc`.
2. `logs_search` → cluster of `JWT signature verification failed: kid=... unknown` errors in `sts-broker`.
3. `trace_get` on a failing request → confirms failure at `sts-broker`'s signature-validation step.
4. `metric_query` → step-change in `sts.jwt_validation_failures` starting T-16h on `cloud-2` only (cloud-1 and cloud-3 flat).
5. `ticket_search` → find `CHG-1891` (OIDC key rotation by `j.patel`).
6. `slack_search` →
   - `j.patel`'s `#sre-oncall` post: *"rotated OIDC signing key, terraform applied to all regions, looks clean."*
   - Earlier same-day thread in `#infra-terraform`: another engineer mentioning Terraform **state-lock contention** during a concurrent run against `cloud-2`.
7. `kb_search` → find the correct "OIDC key rotation runbook" (buried under generic "Terraform best practices" docs) describing the state-lock failure mode and manual recovery steps.
8. Synthesize: `CHG-1891` rotated the key; `cloud-2` apply was silently blocked by state-lock contention; `cloud-2`'s `sts-broker` still holds the stale public key; fix is to re-apply Terraform targeting `cloud-2` only.

### 4.4 Success criteria (how we score)

**Must identify:**
- `CHG-1891` (OIDC key rotation by `j.patel` at T-16h) as the originating change.
- That the apply silently failed on `cloud-2` due to Terraform state-lock contention.
- That `cloud-2`'s `sts-broker` is validating against the stale public key.

**Must propose:**
- Re-apply Terraform targeted at `cloud-2` to push the new public key.

**Must NOT conclude:**
- That the `cloud-3` CPU incident (red herring) is related.
- That the `cloud-1` `policy-svc` deploy (red herring) is related.
- That the rotation should be rolled back globally (wrong fix — would break `cloud-1`/`cloud-3`, which are healthy).

### 4.5 Noise / red herrings built in

| Item | Purpose |
|---|---|
| cloud-3 CPU throttling on `ml-scorer` (separate alert + ticket) | Tests scoping discipline |
| cloud-1 routine `policy-svc v2.14.3` deploy at T-4h | Deploy noise |
| Stale KB doc from 2024 with obsolete log patterns | Tests whether agent over-trusts old docs |
| Unrelated Acme CSM Slack thread from 2 days prior about pricing | Realistic chatter |
| Baseline ~0.8% 5xx rate from a known flaky downstream | Makes "spike" require actual comparison |
| `j.patel`'s confident "looks clean" Slack message | Tests whether agent over-trusts human confirmation vs. cross-checking metrics |

---

## 5. Phased execution plan

### Phase 0 — Spec & paper design ✅ DONE
- Task #1 fully specified on paper (section 4 above).

### Phase 1 — Vertical slice (Task #1 only) — ~1 week
Goal: one working end-to-end task, zero simulator code.

1. Read Meta's OpenEnv repo docs; understand env contract (reset/step/tool registration/reward).
2. Define data schemas — exact fields for a log row, a span, a ticket, a metric sample, a Slack message, a KB doc.
3. Hand-author Task #1 data files:
   - `logs.jsonl` — ~200-500 log lines across 3 clouds, healthy + failing.
   - `traces.json` — 20-30 span trees, matching trace_ids with logs.
   - `metrics.csv` — time-series rows for relevant metrics.
   - `tickets.yaml` — 8 tickets (`INC-4472`, `CHG-1891`, `CHG-1905`, `INC-4470`, 4 unrelated).
   - `slack.yaml` — ~20 messages across 3-4 channels.
   - `kb/` — 6-10 markdown docs (the correct-but-buried one, the stale one, the runbook, filler).
4. Implement the ~10 tools (FastAPI handlers querying DuckDB + SQLite).
5. Wire into OpenEnv.
6. Run Opus through the env; iterate until it can solve Task #1.

### Phase 2 — Task #2 hand-authored + solidify — ~3-4 days
- Author a second task by hand (different incident shape, e.g., network policy / SG change).
- Factor out common schema / infra.
- Confirm Opus struggles where expected and Qwen3-8B fails consistently.

### Phase 3 — Simulator — ~1.5 weeks
- Once the data shape is known from Phases 1-2, build a discrete-event simulator that models services + requests + config timelines. "Incidents" become declarative config perturbations.
- Use the simulator to regenerate Task #1 and #2, then scale to tasks #3-#10.
- Add noise knobs (trace-ID drop rate, service-name aliasing, clock skew) for realism calibration.

### Phase 4 — Full 10 tasks + calibration — ~1-2 weeks
- Write stories + configs for tasks 3-10.
- Generate snapshots.
- Run Opus and Qwen3-8B across all 10; tune difficulty via noise knobs and buried-evidence depth to hit target pass rates.

### Phase 5 — Polish — ~1 week
- LLM-generated filler for realistic Slack/ticket/KB chaff.
- Stale / misleading KB docs written with intention.
- Package for OpenEnv distribution.

**Total rough estimate:** ~5-7 weeks solo.

---

## 6. Key terminology (for the friend)

- **Log** — a timestamped text line emitted by a service. Many per request.
- **Trace** — a tree of "spans" representing one request flowing across services. Tells you where it broke and how long each hop took.
- **Metric** — an aggregated numeric time-series ("auth-svc errors per minute"). Loses per-request detail; good for trend/alert.
- **Coherence rule** — every log line emitted during a request must carry the request's `trace_id`, so you can pivot from "weird log" → "show me the whole trace."
- **OpenEnv** — Meta's framework for building LLM agent environments. Envs run as HTTP services with typed action/observation schemas. Gymnasium-inspired API.
- **Pass@1** — the probability the model solves the task on its first attempt. Standard LLM-eval metric.
- **Trajectory** — the ordered sequence of tool calls + reasoning the model produced while solving a task.

---

## 7. Open questions to resolve

1. **Exact OpenEnv env contract** — need to read the repo to confirm the tool-registration and reward-shape API before locking tool signatures. May shift minor details in Phase 1.
2. **Intended audience for the benchmark** — internal team? public release? affects polish bar.
3. **Is Task #1's IAM-trust-policy-with-array-`aud` shape too AWS-specific?** Alternative: OIDC signing-key rotation variant (admin rotated a secret in cloud-1/3 but forgot cloud-2). Same investigative shape, less AWS trivia.
4. **Telemetry volume target** — spec says "GB/hr"; for a serveable snapshot, we plan ~100-500MB per task, with realism coming from *cardinality* (many services × clouds × tenants × ops) rather than raw volume. Acceptable?

---

## 8. Immediate next steps (this week)

1. Read Meta's OpenEnv repo documentation (1-2 hours).
2. Define the 6 data schemas (log, span, metric, ticket, slack message, KB doc) — one doc, locked before authoring.
3. Hand-author Task #1's data files.
4. Build the tool endpoints over the hand-authored files.
5. Run Opus against it.

---

## 9. Risks

- **Difficulty calibration is empirical, not engineering.** Expect multiple iterations on each task against Opus rollouts. Budget time for it.
- **"Messy but coherent" is the spec's hardest craft bar.** Realism knobs need tuning; easy to either under-mess (too easy) or over-mess (unsolvable).
- **Solo scope.** 10 tasks × realistic data × calibration is genuinely 5-7 weeks. Resist scope creep on any single task.
- **OpenEnv is new.** API may still be shifting; build thin wrappers so framework updates don't require rewriting tools.
