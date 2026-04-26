# Decisions, Insights, and Reasoning Log

> Living record of every meaningful decision we made building this env, why we made it, what alternatives we considered, and what we learned in the process. Source material for the demo video, HF blog post, and any "how we built it" presentation.

> Updated continuously as we make new decisions. Latest entries on top of each section.

---

## Strategic positioning

### Pursue Cloud Sec Env for the hackathon (vs. starting fresh on a simpler theme)

- **Decision:** Build the cloud-security incident-investigation env originally specified in `Environment_Spec.md`, mapped to Theme #3.1 (Professional Tasks / World Modeling).
- **Alternatives considered:** Toy puzzle world (faster but generic), multi-agent negotiation (Theme #1, novel but less rubric-aligned), long-horizon planning (Theme #2 — works as a secondary frame).
- **Reasoning:**
  - Domain depth as moat: most hackathon teams will ship toy environments. Cloud security is a domain that's *hard to fake* and immediately credible to engineering judges.
  - Rubric alignment: 70% of grading weight (40% env innovation + 30% storytelling) rewards exactly what a rich domain like this can deliver.
  - Story-readiness: the OIDC rotation incident is a self-contained narrative arc — alert → investigation → root cause → fix. Maps cleanly to a 2-minute demo.
- **Tradeoff accepted:** higher craft bar than simpler envs. We need messy-but-coherent telemetry, which can't be quickly generated.

### Compress from 10 tasks → 1 flagship task

- **Decision:** Build one task (OIDC key rotation) to demo-quality. Drop the original 10-task scope.
- **Alternatives considered:** 3 tasks (broader benchmark but less polish per task), 10 tasks (original spec, ~5-7 weeks of work).
- **Reasoning:** Judges see a 5-minute demo. They don't grade by task count; they grade by depth and discriminability. One excellent task beats 10 shallow ones.
- **Insight:** The hackathon's "submission" is really a demonstration that the env *could be* a serious benchmark. Adding tasks 2-10 later is mostly data authoring once the infra exists.

### Reallocate effort: 40% env / 30% training / 20% storytelling / 10% buffer

- **Decision:** Move from the original "80% env / 20% other" plan to a more balanced split.
- **Reasoning:** The rubric explicitly rewards "showing improvement in rewards" (20%) + "training pipeline" (10%) = 30% on training-side work. Underinvesting there meant leaving 30% of the grade on the table.
- **Lesson:** Read the rubric multiple times. Easy to misallocate based on which axis feels most fun.

---

## Architecture decisions

### Single `CloudSecAction` with `tool_name` + `arguments` dict (vs. tagged union)

- **Decision:** One unified action type. `tool_name` selects the tool (or `submit_answer` for terminal). `arguments` is a flexible dict, validated server-side per-tool.
- **Alternatives considered:** Tagged union (`CallToolAction | SubmitAnswerAction`) with discriminator field; per-tool typed action classes.
- **Reasoning:** LLMs are trained heavily on the `{name, arguments}` function-calling shape (OpenAI, Anthropic, every modern LLM API uses this). Matching it gives the agent the easiest learning target. Type-safety at the action level would just duplicate per-tool server validation.
- **Result:** When we built both adapters (Anthropic native tool-use + Qwen prompted JSON), neither needed special-cased handling. Same shape across both.

### Observation: `content` for the LLM, `data` for the scorer

- **Decision:** `CloudSecObservation` has parallel fields — `content: str` (human-readable text) and `data: dict` (structured mirror).
- **Reasoning:** LLMs natively consume text; making them parse JSON wastes tokens. But the reward scorer needs structured access for "did the trajectory contain CHG-1891?" lookups. Lossy round-trip would kill the trajectory-grading dimension.
- **Insight:** Real production tool-use APIs (Anthropic, OpenAI) encode tool results as text strings for the same reason. Our split mirrors that pattern.

### `observation_type` enum: `alert` / `tool_result` / `error` / `evaluation`

- **Decision:** Tag every observation with a category so the scorer can switch on it cleanly.
- **Reasoning:** Otherwise scorer code becomes brittle string-matching ("is this an error or a real result?"). Enum gives us clear dispatch.

### Errors are observations, not exceptions (the agent retries)

- **Decision:** When the agent calls a tool with bad args (`cloud="cloud-7"`, unknown tool name), the env returns `observation_type="error"` with a helpful message. Episode does NOT terminate.
- **Reasoning:** Real APIs return error responses; agents retry. Forcing termination on the first malformed call would punish exploratory queries unfairly.
- **Tradeoff:** A pathological agent could spam errors all 30 steps. We accept this because reasonable agents course-correct on the first error.

---

## Scenario design (Task #1)

### Swap from AWS IAM `aud`-claim bug → OIDC key rotation

- **Original scenario:** `j.patel` tightened a Terraform IAM trust policy with `"StringEquals": {"aud": "..."}` — but Acme's Okta sends `aud` as a JSON array, and `StringEquals` fails silently on array claims (correct operator: `ForAnyValue:StringEquals`).
- **Final scenario:** `j.patel` rotated the OIDC signing key via Terraform; the apply silently failed on cloud-2 due to state-lock contention with `m.chen`'s concurrent run. cloud-2's sts-broker still has the old public key; Acme JWTs fail signature verification.
- **Reasoning:** Both have the same investigative shape (scoping discipline + change correlation + slack/KB cross-reference + falsification). But the IAM `aud`-claim bug requires audience-level AWS IAM trivia knowledge — the kind of thing that would derail a 2-minute demo because most viewers don't know that `StringEquals` operates on string values not arrays.
- **OIDC variant works in a single sentence demo:** *"An SRE rotated the OIDC key. The change landed in two regions but silently failed in the third. Users routing to the broken region can't log in."*
- **Lesson:** Realism without obscurity. A scenario only works for a demo if the failure mode is *one-sentence-explainable* without specialized vocabulary.

### Add CHG-1888 as a competing hypothesis (the falsification trap)

- **Decision (made during calibration):** Insert a second change ticket — same author (`j.patel`), same service (`sts-broker`), one day earlier — that produces benign WARN logs on cloud-2. Add corroborating Slack chatter and cross-cloud log evidence.
- **Disambiguating signal designed in:** CHG-1888 shipped to cloud-1 AND cloud-2 (not cloud-3). If CHG-1888 caused the outage, cloud-1 would also show failures. cloud-1 is healthy → CHG-1888 *cannot* be the cause. Only CHG-1891 (the silent failure on cloud-2 alone) explains the cloud-asymmetric pattern.
- **Reasoning:** This is the single biggest difficulty change we made. The original scenario had ONE plausible candidate; Opus solved it linearly. Adding CHG-1888 forces *elimination reasoning* — the senior-SRE skill of falsifying alternatives, not just identifying the right answer.
- **Outcome:** Opus consistently identifies CHG-1891 correctly *but never explicitly rules out CHG-1888.* The `explicit_elimination` rubric dimension catches this every time. Drove Opus Pass@1 from ~80% (under the previous keyword rubric) to ~0% (perfect score) under the new rubric.

### Realistic messiness: trace_ids missing, service-name aliasing, partial spans, stale KB doc

- **Decisions:**
  - 5-7 log lines have `trace_id: null` (audit-logger / pre-context errors).
  - One trace (`a1b2c4`) is flagged `partial: true` with 3/5 spans present.
  - kb-09 is dated 2024 with a "historical reference only" warning box, references a retired library.
  - Patel's overconfident "looks clean" Slack post is a deliberate trap.
- **Reasoning:** Production observability data is messy in *specific structured ways*, not random. We modeled the patterns that actually show up: un-instrumented sources lose trace_ids, sampling drops spans, old docs get left behind, humans get overconfident. Random noise would make the env feel fake; structured mess makes it feel real.

### Tool surface: 6 tools (compressed from spec's 10)

- **Decision:** logs_search, trace_get, metric_query, ticket_search, slack_search, kb_search. Plus `submit_answer` as the terminal pseudo-tool.
- **Dropped:** `list_deployments` (covered by `ticket_search type=CHG`), `list_services` (services are an enum, no need to list), `trace_search` (in practice agents always find trace_ids in logs first; standalone trace search isn't a realistic workflow).
- **Reasoning:** Each extra tool adds surface area for malformed calls and cognitive load on the agent. 6 covers every workflow we actually need; 10 was over-engineered.
- **Lesson:** "What does an SRE actually do?" is a better tool-design question than "what queries does the data support?". The latter leads to over-tooling.

---

## Reward function design — the iterative journey

This is where the most thinking went. The journey from naive keyword-matching to the trajectory-aware composable rubric we have now had four major rounds.

### Round 0: keyword-matching rubric (initial)

- **Design:** Each rubric component checks for substring presence: "CHG-1891" in answer → +0.25, "state lock" in answer → +0.20, etc.
- **Why we started here:** Fast, deterministic, easy to debug.
- **Result:** Opus Pass@1 = 100% across 5 rollouts. Mean 1.0. **Too easy.**
- **Insight:** A rubric that tests vocabulary doesn't test understanding. Opus mentions every required keyword for free — they're in the system prompt and the data.

### Round 1: stricter keyword rubric (compound conditions)

- **Design:** Each component now requires multiple conditions to all be true. `identify_chg_1891` requires both `chg-1891` AND `j.patel`. `identify_state_lock_mechanism` requires `state lock` AND (`m.chen` OR `concurrent`). `identify_cloud2_scope` requires `cloud-2` AND (explicit "only" OR mentions of cloud-1 + cloud-3).
- **Reasoning:** Force specificity. Generic mentions shouldn't score.
- **Result:** Opus Pass@1 dropped 100% → 80%. Mean 0.94.
- **Insight:** Better, but still a string-matching exercise. The real failure mode is *what Opus doesn't say* (alternative-elimination, hedging, evidence backing) — string-match can't catch absence-of-things.

### Round 2: LLM-as-judge with continuous 0-1 scoring

- **Design:** Replace keyword rubric with a Claude Sonnet 4.6 call that grades each dimension on a 0-1 scale with per-dimension justifications. Same 6 dimensions + 2 bonuses (`cites_specific_evidence`, `falsifies_red_herrings`).
- **Reasoning:**
  - Continuous scoring (0-1) > binary (pass/fail). Vague answers score 0.5; clear answers score 1.0.
  - Justifications make the rubric explainable — useful for the demo and for improving the prompt iteratively.
  - This is how real benchmarks (Arena Hard, MT-Bench, AlpacaEval) score answers in 2024+.
- **Result:** Opus Pass@1 (threshold 1.0) = 80%. Mean reward 0.985 (down from 1.0). The judge caught real gaps — Opus got 0.925 on one rollout for forgetting `j.patel` and not falsifying any red herring.
- **Insight:** The judge worked, but Opus's answers were genuinely so thorough that it usually scored ~1.0 anyway. **The bottleneck wasn't the rubric — it was the task itself.** A rubric can only discriminate among answers; if the task only has one path to one answer, a thorough agent will hit them all.

### Round 3: trajectory-aware rubric (the innovation)

- **Design:** Major redesign. Two new core dimensions added:
  - **`evidence_supported_claims`** (weight 0.10): the judge receives the agent's full trajectory. For each claim in the answer, it checks whether the trajectory contains tool-call evidence for that claim. Hallucinated claims score 0.
  - **`explicit_elimination`** (weight 0.10): rewards the answer for naming an alternative hypothesis AND ruling it out with a specific reason. Score 0 if no alternative is mentioned.
- **Plus the data change:** added CHG-1888 as a tempting wrong hypothesis (see above).
- **Reasoning:**
  - **Evidence-supported scoring** captures *grounded reasoning*: an agent that emits the right answer without investigating gets 0 on this dimension. **Hard to game.** This is the hackathon docs' explicit ask: "Is hard to game; an agent that exploits the reward without solving the task should not get high scores."
  - **Explicit-elimination** captures *senior-SRE falsification skill*: the move of naming an alternative and proving it's not the cause. Junior engineers find answers; senior engineers rule out wrong ones.
- **Result:** Opus Pass@1 (perfect) = **0%**. Mean reward = **0.922**. The `explicit_elimination` dimension scored 0.0 on every single Opus rollout — a consistent, diagnostic failure mode.
- **Insight:** You don't make a task hard by hiding the answer. You make it hard by **requiring something the LLM doesn't naturally do** (in this case: explicitly considering alternatives). The reward signal is then the lever — it rewards the absent skill, which fine-tuning can teach.

### Step-level rewards: 8 dimensions (separate from terminal)

- **Design:** During the episode, each tool call earns small step-level rewards:
  - +0.10 `correct_first_tool` (logs_search scoped to cloud-2 on step 1)
  - +0.10 `finds_signature_error_log`
  - +0.05 `pivots_to_trace` (trace_get on a trace_id seen in logs)
  - +0.10 `finds_chg_1891_ticket`
  - +0.10 `reads_state_lock_slack`
  - +0.10 `finds_correct_runbook` (kb-42)
  - −0.05 `penalty_no_scoping` (logs_search without cloud or service filter)
  - −0.10 `penalty_cloud3_fixation` (3+ consecutive cloud-3-scoped calls)
- **Reasoning:** Dense training signal. Without per-step rewards, training only sees terminal pass/fail — extremely sparse. With per-step rewards, every action has gradient.
- **Insight:** Step rewards use *one-shot achievements* (earned once per episode) for positives, but *recurring penalties* for negatives. Asymmetric on purpose: rewards are upper-bounded so the agent can't farm them; penalties keep applying so persistent bad behavior keeps costing.

---

## Difficulty calibration (the empirical loop)

The biggest single insight from the build: difficulty isn't designed, it's **measured and tuned**.

### The measurement protocol we settled on

For each round of changes:
1. Run 5 Opus rollouts at temp 0.7
2. Compute Pass@1 at thresholds (1.0, 0.95, 0.9, 0.85)
3. Compute mean reward
4. Inspect the rubric breakdown for one passing and one failing rollout
5. Identify *which dimension* discriminated

The dimension-level breakdown was the key — it told us *what specifically Opus did wrong*, which let us target the next change.

### Pass@1 vs. mean reward — both matter, for different reasons

- **Pass@1** is the spec criterion ("Opus Pass@1 < 50%"). Binary metric.
- **Mean reward** is the training signal. Continuous metric.
- **Insight:** A task where Opus mean = 0.95 but Pass@1 (threshold 1.0) = 5% is *good for difficulty showcasing* but *bad for SFT training data quality* (most trajectories miss something different). A task where Opus mean = 0.85 but Pass@1 (threshold 1.0) = 0% with a *consistent* missing dimension is **the sweet spot** — every passing trajectory is good training data, and the task has clear difficulty.
- We landed at the second case.

### Tracking what changed across rounds

| Round | Change | Opus Pass@1 (threshold 1.0) | Mean | Notes |
|---|---|---|---|---|
| 0 | Initial (keyword rubric) | 100% | 1.000 | Too easy |
| 1 | Stricter keyword rubric | 80% | 0.94 | Better but still keyword-game |
| 2 | LLM-as-judge | 80% | 0.985 | Judge works, but task too easy |
| 3 | + CHG-1888 + 2 new dims | **0%** | **0.922** | Locked here |

### Lesson: don't chase difficulty by adding random noise

- Tempting alternative we considered: drop trace_ids randomly, add inconsistencies, shorten step budget.
- Why we didn't: each of those breaks *realism*. An env that's hard because it's noisy isn't pushing frontier model capability — it's just frustrating. We wanted hard *because the task requires real reasoning*.
- The CHG-1888 + elimination-rubric move is hard on a *legitimate* axis: it's the kind of senior-SRE thinking the model can demonstrably learn.

---

## Engineering decisions

### Adapter abstraction (`BaseAdapter`) so different LLMs slot in without changing the harness

- **Decision:** Define a `BaseAdapter` interface (`reset` / `get_action` / `observe`) with concrete implementations: `AnthropicAdapter` (native tool-use), `QwenAdapter` (prompted JSON over HF Inference).
- **Reasoning:** We want to evaluate Opus, fine-tuned Qwen, and (potentially) other models with the same harness. Putting the LLM-specific quirks behind an adapter keeps `RolloutHarness` model-agnostic.

### Anthropic adapter quirks (3 bugs caught)

1. **`temperature` deprecated for Opus 4.7** — model rejects the parameter. Fix: skip `temperature` for any model name containing `opus-4-7`.
2. **Response content is SDK objects, not dicts** — appending `response.content` raw back into messages tripped the API. Fix: explicitly serialize text and tool_use blocks into plain dicts.
3. **Parallel tool use** — Opus returns multiple tool_use blocks per response by default. Our env is episode-based (one action per step). Fix: pass `tool_choice={"type": "auto", "disable_parallel_tool_use": True}`.
- **Lesson:** Provider-specific tool-use APIs are uneven across models. The smoothest abstraction would be agnostic JSON, which is what we did for Qwen.

### Qwen adapter: prompted JSON tool-calling (not native tool-use)

- **Decision:** Format the 7 tools as JSON schemas in the system prompt; require Qwen to respond with a strict JSON object `{tool_name, arguments, reasoning}`. Parse on the client side with robust JSON extraction (handles markdown fences, extra prose, brace-counting fallback).
- **Alternatives considered:** Native tool-calling APIs (Together AI, Fireworks, OpenAI-compatible providers).
- **Reasoning:**
  - **Provider-agnostic:** the same code works against HF Inference, local Ollama, vLLM, anything.
  - **Distribution-match for SFT:** we'll fine-tune Qwen on Opus trajectories. The fine-tuning data format will be `{tool_name, arguments}` JSON. Using prompted JSON at baseline eval ensures *no distribution shift* between baseline and fine-tuned eval — same prompt, same expected output format.
- **Lesson:** Adapter design choices have downstream consequences. Picking native tool-use for Qwen would have created a baseline-vs-fine-tuned format mismatch we'd then have to paper over.

### Storing reward scoring as a separate module (`reward.py`) and judge as another (`llm_judge.py`)

- **Decision:** `RewardScorer` is independent of the env. `LLMJudge` is independent of `RewardScorer`. They compose: env → scorer → optional judge.
- **Reasoning:** The hackathon docs explicitly ask for "composable rubrics." Each scoring component should be a separate, swappable piece. A future researcher could swap our LLM judge for a different one (rule-based, code-execution-grounded, multi-judge ensemble) without touching the env.
- **Insight:** This is the **rubric system thoughtfulness** the docs reward.

### .env-based credentials with provider-specific guards

- **Decision:** `.env` for `ANTHROPIC_API_KEY` and `HF_TOKEN`; `run.py` checks the right one based on the model name prefix; `.gitignore` excludes the file.
- **Reasoning:** A 12-factor-app pattern keeps secrets out of source control and lets us swap providers without code changes.

---

## Tooling choices: HuggingFace Inference vs. local vs. paid providers

- **First try:** HF serverless inference (free tier).
- **Result:** Hit `402 Payment Required` after one rollout. HF's free tier is exhausted before we can even baseline.
- **Decision:** Defer Qwen baseline measurement to Colab during fine-tuning (Tasks #14 + #16). The model weights will already be loaded there; running inference in the same Colab kernel is free and natural.
- **Insight:** Don't pay (HF PRO $9/month) when there's a free path that arrives later in the pipeline anyway. Save the credits for actually running the demo.

### One Qwen rollout's worth of free data was enough

Even though we ran out of credits on Qwen, the one completed rollout told us:
- Qwen scoped correctly to cloud-2 auth-svc on step 1 (good)
- Qwen found the correct kb-42 runbook on step 6 (good)
- Qwen never searched for "OIDC" in tickets (missed CHG-1891)
- Qwen used too-narrow time window (T-60m..T+0; the smoking gun is at T-14h)
- Qwen **hallucinated a trace_id** (`T-14465872346578901234567890`) — generated a fake ID instead of using one from logs
- Qwen never reached `submit_answer` — eventually output unparseable JSON

**Insight:** *What Qwen does wrong is exactly what we'd expect a small model to do wrong on this kind of task.* Hallucination, narrow scoping, repetitive queries. These are concrete failure modes our SFT training will target.

---

## What we explicitly chose NOT to do (and why)

- **Build a data simulator.** The 5-7 week original plan included a discrete-event simulator for generating data at volume. We hand-authored Task #1's data instead. Reasoning: forcing ourselves to feel what "coherent" and "realistic" mean by typing the data is more valuable than building generation infrastructure for one task.
- **Live (dynamic) env.** Each task is a frozen snapshot. Agent actions don't mutate state. Reasoning: ~5x less work than a live simulation, and nothing about Task #1's investigation requires the world to change during the agent's investigation.
- **Per-tool typed argument classes.** Could've defined `LogsSearchArgs`, `TraceGetArgs`, etc. Instead, `arguments: dict[str, Any]` validated server-side. Reasoning: matches the LLM's preferred shape (function-calling JSON); per-tool typing would just duplicate server-side validation.
- **Run baseline Qwen via paid HF tier ($9 PRO).** When free tier hit limits, we deferred to Colab where the weights are already loaded. Saved the spend.
- **Add MORE red herrings beyond CHG-1888.** Tempting to keep adding ambiguity. Resisted. Each red herring should pull weight; piling them on starts to feel adversarial rather than realistic.
- **Use RL (GRPO/PPO) instead of SFT.** First-time fine-tuners + 48-hour budget. SFT on harvested Opus trajectories is dramatically lower-risk and produces a clean training curve. Reasoning: pick the simplest tool that hits the rubric.

---

## Cross-cutting insights

### "Hard to game" is the most important property

The hackathon docs said it explicitly: an agent that exploits the reward without solving the task shouldn't score well. Our `evidence_supported_claims` dimension is the load-bearing piece for this — an agent can't just emit the correct answer (which is in the system prompt's general knowledge) without doing the investigation, because the trajectory will be inspected for evidence.

### Difficulty comes from requiring negative-space reasoning

Our biggest difficulty jump came from making the agent *rule out* alternatives, not from making the right answer harder to find. Pattern-matching the right answer is what LLMs are good at; ruling out wrong ones is what they're bad at. **The reward should target the gap, not the strength.**

### Composable rubrics are real, not just a buzzword

We have three independent scoring components — keyword rubric (fallback), LLM judge (default), step-level achievements. They compose freely. Anyone can disable the judge via `CLOUD_SEC_DISABLE_JUDGE=1` env var and fall back to keyword rubric for fast training loops. They can re-enable for high-fidelity eval.

### Trajectory > answer

The shift from grading the answer alone to grading the answer-plus-trajectory was the biggest single quality jump. It mirrors how real engineering review works — we don't just ask "is the conclusion right?" we ask "is the work that led to the conclusion sound?".

### LLM-as-judge is approachable for hackathon scope

The cost is small ($0.02-0.05 per episode). The latency is acceptable (~3-5 seconds per terminal grade). The discrimination is dramatically better than keyword matching. There's no good reason for a benchmark in 2026 to not use one.

---

## Mid-hackathon strategic pivots (added during work)

### Diagnostic discovery: most "Opus difficulty" was prompt-omission, not task hardness

After running 4 calibration rounds trying to push Opus Pass@1 below 50%, we ran a clean diagnostic: **update the system prompt to ask explicitly for elimination reasoning** (the rubric dimension Opus was failing). Result: 5/5 rollouts at terminal=1.0. The "0% Pass@1" we'd been celebrating was an artifact of prompt omission — we'd been penalising Opus for not doing something we never asked it to do. Real fairness test fixed this.

**Lesson:** before claiming a model "can't do X," check that you actually asked it to do X. Prompt construction is part of the eval setup.

### The SFT-vs-RL contradiction we caught late

The "Opus Pass@1 < 50%" goal lives in our internal `Environment_Spec.md` and has an *RL framing*: in RL, reward signal directly trains the agent, so a hard task is the goal. But our planned training approach was *SFT* on Opus trajectories, where Opus is the **teacher** — and an unsuccessful teacher produces bad training data.

These two goals contradict. We spent multiple calibration rounds trying to make Opus fail, which directly damages the SFT data quality.

**Lesson:** the reason for "make the task hard" is approach-dependent. Under RL, hard = good signal. Under SFT, the teacher must succeed (the task can still be hard for the *student*).

### Decision: pivot to SFT-then-GRPO hybrid

After researching the OpenEnv ecosystem (TRL, Unsloth, ART, torchforge, SkyRL), we found that:
- Every canonical OpenEnv training example uses GRPO (TRL's `GRPOTrainer` is the reference pattern)
- Every successful example is on simpler tasks (BlackJack 2-action; Wordle 1-tool; 2048 4-action)
- No public success exists for a 6-tool agentic env trained via GRPO in a hackathon timeline
- The closest parallel (LinkedIn's GPT-OSS retrospective) used 16 H100 nodes over multiple days
- GRPO requires non-zero baseline success to learn (group reward variance) — and our Qwen baseline submitted only 40% of rollouts

The hybrid plan:
1. **SFT first** (proven path, Person B's pipeline already de-risked): Qwen 0% → ~40-60% via behavioral cloning of Opus's near-perfect trajectories.
2. **GRPO on top of the SFT model** (if time permits): refines the model with env reward signal directly.

This way the floor (SFT) ships even if the ceiling (GRPO) doesn't converge.

### Architecture: keyword rubric primary, LLM judge auxiliary

Initially the LLM-as-judge was the *primary* terminal reward when an `ANTHROPIC_API_KEY` was set. Reproducibility concern: hackathon judges running our env without an API key would lose the rich rubric. Plus: GRPO training needs fast deterministic rewards (LLM judges are slow + noisy).

**Rearchitected:** keyword rubric is now ALWAYS the primary `reward` field. The LLM judge runs as an *auxiliary* layer (when API key available) and writes to `metadata._judge` for richer offline inspection. Best of both worlds:
- Reproducibility: works without API key
- RL-friendly: deterministic, fast primary reward
- Richer eval: judge layer available to researchers

### Qwen baseline measurement (n=5, post-architecture-flip)

| Metric | Value |
|---|---|
| Submission completion rate | 40% (2/5) — others died on JSON parsing |
| Best terminal reward | 0.365 (LLM-judge era) |
| Mean reward across all 5 | ~0.073 |
| Failure mode | Adapter JSON parse errors + early-give-up at step 5-10 |

Crucially, when Qwen does submit, it shows partial reasoning ("signing key configuration", "state lock contention" mentioned but vague). This is exactly the kind of partial-success baseline that SFT can bootstrap.

13× gap from Opus (0.073 → 0.98). Plenty of headroom for training improvement.

## Final SFT result (n=5 against deployed Space, 2026-04-26)

After several infra detours (Colab T4 OOM, AutoTrain `all-linear` vocab-mismatch landmine, transformers 5.x BatchEncoding API change, HF default Inference Toolkit OOM on A10G), eval finally landed on **HF Inference Endpoints (A100) + the cleaned adapter (`Krishna3451112/cloud-sec-clean`)** driven from a CPU-only Python script that hits both the endpoint and the deployed env Space over HTTP.

| Metric | Value |
|---|---|
| Submission rate | **100% (5/5)** |
| Mean terminal reward | **0.900** (deterministic keyword rubric) |
| Mean total reward (terminal + step rewards) | 1.800 |
| Mean steps per episode | 18.0 |
| Decoding | Greedy (`do_sample=False`) |

Each episode followed essentially the same investigation arc Opus would: `kb_search` → scoped `logs_search` (cloud-2 + auth-svc) → `ticket_search` finding CHG-1891 → `slack_search` for the m.chen state-lock thread → `metric_query` to verify scope → `submit_answer` with the full root-cause + fix paragraph at step 18.

**Headline takeaway:** SFT on 55 trajectories closed ~95% of the Opus-gap on this task (0.05 → 0.900 vs Opus 0.96 ceiling). The remaining 0.06 is `avoids_global_rollback` (a phrasing trap); the model gets every other rubric dimension.

### What we learned along the way

- **AutoTrain's `target_modules=all-linear` + `add_eos_token=True` is a landmine.** Combination causes the saved adapter to bundle full retrained `embed_tokens` + `lm_head` matrices at the tokenizer's actual vocab size (151665), which won't fit any standard Qwen base loaded at the padded size (152064). Solution: post-hoc strip those layers from the safetensors + adapter_config; the LoRA on attention/MLP layers carries ~95% of the learning anyway.
- **HF Inference Endpoints default toolkit OOMs on A10G (24 GB) for Qwen 7B.** Bump to A100 or pre-merge the adapter and deploy the merged model.
- **The SFT'd model emits literal `\n` between JSON fields** (a tokenization artifact from how Opus's JSON dumps got encoded in training). Tolerant JSON parser (strip `\n` and `\t` outside strings before json.loads) handles it cleanly.
- **Greedy decoding is essential for first-rollout sanity.** SFT'd models on small datasets are sensitive to temperature; sampling can knock them off the learned format. Ship greedy as the default eval mode.

## Open items (post-submission)

- Run the rubric ablation with judge column populated (~$0.30 of API spend) for the demo narrative.
- GRPO recipe (`colab/cloud_sec_env_grpo.ipynb`) ships as scaffolding — never executed during the hackathon.
- Tasks 02-10: the env framework supports them; they're data-authoring exercises against the same harness.
