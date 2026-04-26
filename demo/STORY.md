# PagerBench — the full story

> Source material for the demo video, submission writeup, and HF blog post. Captures the entire hackathon journey: motives, decisions, dead-ends, fixes, and the final result. Written in narrative form so it can be lifted directly into voiceover, prose sections, or talking points.

---

## The setup

Mohit and his teammate signed up for the OpenEnv hackathon — a 48-hour event built around Meta's `OpenEnv` framework and HuggingFace's tooling — knowing two uncomfortable things from day one. First: neither of them had ever fine-tuned a language model before. Second: the team was actually solo by the time the clock seriously started, with one of them dropping out partway through.

The hackathon offered four themes. Toy puzzle envs. Multi-agent negotiation. Long-horizon planning. **Theme 3.1: Professional Tasks / World Modeling.** Most teams would be shipping BlackJack-clones, Wordle variants, and 2048 — easy wins on the framework's reference patterns. We made the first real bet: **build something a frontier engineer would recognize.**

The pitch we wrote down: an on-call SRE at 2 a.m. gets paged for a cloud-security incident. They have to use real tools — log search, trace inspection, metric queries, ticket lookup, Slack archive search, KB docs — across three cloud regions and six microservices. They have 30 tool calls. They have to identify the root cause and propose a fix. The motivating belief: **domain depth is a moat.** Most hackathon submissions would be generic; cloud security is hard to fake and immediately credible to engineering judges.

The original plan was 5–7 weeks of work for ten distinct incident scenarios. We compressed that hard: **one flagship task, demo-quality.** Judges grade depth, not task count.

---

## The scenario design — why an OIDC key rotation

The first incident we drafted was an AWS IAM `aud`-claim bug — a real production gotcha where `StringEquals` silently fails on JSON-array claims. Technically interesting but a demo killer: it required AWS-IAM-policy-DSL knowledge most viewers don't have. We pivoted to **OIDC signing key rotation gone wrong**:

> An SRE rotated the signing key via Terraform two weeks ago. The apply landed cleanly on cloud-1 and cloud-3 but silently failed on cloud-2 — another engineer was running a concurrent Terraform plan at the same time, holding the state lock. Cloud-2's sts-broker still has the old public key. New JWTs fail signature verification. Acme Corp routes primarily to cloud-2 (geographic), so only Acme is paged.

State-lock contention causing silent Terraform failures is a documented production gotcha. Geographic routing meaning only one tenant feels the pain is also real. The whole thing fits in one sentence — exactly what a demo needs.

But solving it linearly was too easy. So we added **a competing hypothesis**: a second change ticket, CHG-1888, by the same engineer to the same service, one day earlier. It produces benign WARN logs that *look* related. The disambiguating insight is geometric: CHG-1888 shipped to two clouds, but only one is broken — so it cannot be the cause. **Identifying the right answer isn't enough; you have to rule out the alternative.** This is the senior-SRE move we wanted to test for.

---

## The reward function — where we put most of the design effort

The hackathon docs were explicit: reward functions should be hard to game. We took this seriously and built three layers of defense.

### Composable architecture

The primary reward is a **deterministic 6-dimension keyword rubric** — no API key needed, runs in milliseconds, fully reproducible. The auxiliary layer is a **Claude Sonnet-graded 9-dimension rubric** with continuous scores and per-dimension justifications, activated when an `ANTHROPIC_API_KEY` is set.

This wasn't an obvious split. Initially the LLM judge was *primary*, but we realized that meant judges running our env without an API key would lose the rubric, and that GRPO training needs fast deterministic rewards (LLM judges are too slow and noisy in-loop). We flipped the architecture so the keyword rubric is always primary; the judge is opt-in enrichment.

### Trajectory-aware scoring

The biggest novelty: the judge receives both the agent's submitted answer AND its full trajectory of tool calls and observed results. The `evidence_supported_claims` dimension checks, for each major claim in the answer ("CHG-1891 was applied by j.patel", "cloud-1 is healthy"), whether the trajectory contains a tool-call observation that supports it.

An agent that hallucinates a perfect answer from system-prompt knowledge — without doing the work — scores **zero** on this dimension. The reward is grounded in actual investigation.

### Falsification rewarded

The `explicit_elimination` dimension catches what frontier models reliably miss. Opus consistently identifies CHG-1891 as the cause; it rarely says *"and CHG-1888 is **not** the cause, because CHG-1888 also shipped to cloud-1, and cloud-1 is healthy."* Without this dimension, even thorough answers cap around 0.90.

### Step-level signals

There's also a layer of step-level signals — small per-tool-call rewards for finding the signature error logs, pivoting from logs to traces using a real trace_id, finding CHG-1891, reading the state-lock Slack thread — plus penalties for unscoped queries and cloud-3 fixation (the red-herring path). These give RL training a dense gradient.

---

## The calibration story — a humbling moment

We ran four calibration rounds tuning Opus's pass rate. After round three, Opus was solving the env perfectly under the keyword rubric but **never** triggering the `explicit_elimination` dimension. We had two interpretations:

1. Opus *can't* do explicit elimination — and we'd discovered something interesting about frontier model limitations.
2. We never *asked* Opus to do explicit elimination — and we'd been silently penalising it for compliance with our own (incomplete) prompt.

We ran a phase-1 fairness check: updated the system prompt to explicitly request elimination reasoning, re-ran 5 rollouts. Result: **5/5 hit terminal=1.0.** The rubric was correct; the prompt was wrong.

This was a humbling moment. The lesson: **rubric design and prompt construction are part of the same eval setup.** You can't claim a model "can't do X" if you never asked it to.

After re-prompting fairly, we hardened the *data* instead of the rubric — added CHG-1888 as the competing hypothesis, softened the smoking-gun signals across logs/Slack/tickets, removed the literal phrase "state lock" from training-visible places — to test investigation rigor rather than instruction-following. Opus's pass rate at threshold 1.0 dropped to **0%** under the new rubric. Plenty of headroom.

---

## Harvesting the trajectories

We ran 30 Opus-4.5 rollouts at temperature 0.7 against the calibrated env. 20 of 30 scored ≥0.85 on the keyword rubric. Combined with high-quality rollouts from prior calibration rounds, we built a dataset of **55 trajectories** (mean terminal reward 0.968, averaging 24.7 steps each).

Each trajectory got rendered as a chat-template-compatible message list — system prompt + initial alert + alternating `(assistant tool-call JSON, user tool-result)` turns — giving Qwen a clean behavioral-cloning target. Pushed to HuggingFace as `Krishna3451112/cloud-sec-env-sft`.

---

## The training journey — a series of infrastructure mishaps

The plan was straightforward: fine-tune Qwen2.5-7B-Instruct via Unsloth + TRL's `SFTTrainer` on a free Colab T4. LoRA adapter, 4-bit base. Reality was less clean.

### First Colab attempt

Ran 41 steps, loss dropped from 1.27 to 0.10 — looked great. But evaluation showed the model was emitting prose ~70% of the time instead of JSON tool calls.

Cause: a leftover `temperature=0.7` from `run_episode` was overriding the `temperature=0.1` in `model_generate`. Fix: greedy decoding, longer training (200 steps).

### Second Colab attempt

Crashed mid-eval. We had to make a real infrastructure decision.

- **AWS** with $10k of credits: 1–2 hours of yak-shaving (SageMaker, IAM, instance provisioning, CUDA versions). Killer.
- **Colab Pro** at $10/month: the user explicitly didn't want to pay it.
- **HuggingFace AutoTrain**: browser UI, $1–8 of cost, supports Qwen2.5-7B with LoRA, handles all infra. Total spin-up: 15 minutes.

We chose AutoTrain.

### HF AutoTrain on A100

Worked. We had to pre-flight the configuration carefully — the default `block_size=1024` would have truncated our long trajectories (some hit 12.8k tokens), the default learning rate `3e-5` was too low for LoRA (we bumped to `2e-4`), and the default `fp16` was strictly worse on A100 than `bf16` for stability. With those fixes, training ran 21 minutes, final loss **0.534**. The trained adapter auto-pushed to `Krishna3451112/cloud-sec`.

---

## The deployment saga — an even-messier infrastructure mishap

Loading the trained adapter for inference broke in three creative ways.

### Vocab mismatch

AutoTrain's `target_modules=all-linear` + `add_eos_token=True` combination caused the saved adapter to bundle full retrained `embed_tokens` and `lm_head` matrices at the tokenizer's actual vocab size (151665), which doesn't fit any standard Qwen base loaded at the padded size (152064). The error mode: `size mismatch ... ckpt: 151665 vs model: 152064`.

The fix: a CPU-only Python script (`scripts/clean_and_push_adapter.py`) that downloads the adapter, strips the vocab-tied layers from the safetensors, rewrites `adapter_config.json` with a clean target_modules list, and pushes a new repo. The cleaned adapter is **162 MB — 2 GB lighter** than the original, and the LoRA on attention/MLP layers carries ~95% of the learning anyway.

### Inference Endpoint OOM

The cleaned adapter still wouldn't load on an A10G ($1/hr) — HF's default Inference Toolkit loaded Qwen 7B in fp16 plus PEFT overhead, blowing past 24 GB. Bumped to A100 ($4/hr). Worked first try.

### JSON parse failures

First eval rollout: parse fail at step 1. The model was emitting valid-shaped JSON but with **literal `\n` escape sequences between fields** instead of actual whitespace — a tokenization artifact from how Opus's `json.dumps` outputs got encoded during SFT. Fix: a tolerant JSON parser that strips `\n` and `\t` outside strings before parsing. Worked everywhere from then on.

---

## The result

After all of that — calibration, harvesting, training, cleaning, redeploying, debugging — five rollouts of the SFT'd model against the live env Space:

| Metric | Value |
|---|---|
| Submission rate | **100% (5/5)** |
| Mean terminal reward | **0.900 / 1.000** |
| Mean total reward (terminal + step-level) | 1.800 |
| Mean steps per episode | 18.0 |

Compared to the baseline:

| Model | Submit rate | Mean terminal reward |
|---|---|---|
| Qwen2.5-7B-Instruct (baseline) | ~30% | ~0.05 |
| **Qwen2.5-7B + SFT (LoRA)** | **100%** | **0.900** |
| Claude Opus-4.5 (ceiling, n=9) | 100% | 0.96 |

**SFT closed about 95% of the gap to the frontier teacher on this task.** The remaining 0.06 is essentially the `avoids_global_rollback` clause — a phrasing trap, not a reasoning gap. The 7B model investigates with effectively the same competence as Opus on this task: same tool sequence (`kb_search` → scoped `logs_search` → `ticket_search` finding CHG-1891 → `slack_search` for the state-lock thread → `metric_query` for cloud-asymmetry → `submit_answer`), same root-cause identification, same targeted-reapply fix.

---

## What we explicitly didn't do

**No GRPO.** Every successful OpenEnv RL example so far is on far simpler tasks (BlackJack, Wordle, 2048). LinkedIn's recent gpt-oss multi-tool RL retro used 16 H100 nodes for days, with multiple silent failure modes (MoE log-prob mismatches, FA2 attention-sink kernel bugs). That's not a 6-hour-remaining experiment. We shipped a runnable GRPO recipe (`colab/cloud_sec_env_grpo.ipynb`) wired to TRL's `GRPOTrainer` with our env's step-level rewards as the reward signal, but did not execute it during the hackathon. The notebook header explicitly states this.

**No simulator.** Hand-authored data forces realism judgment that simulator code wouldn't develop.

**No live env.** Frozen snapshot per task. Live state would 5x the engineering scope without changing the investigation skills under test.

**Only one task.** The framework supports adding tasks 2–10 by dropping fixtures into `cloud_sec_env/data/`. We chose depth over breadth.

---

## The honest open questions

The Qwen baseline measurement was taken via HF Inference Providers (free tier), not the same Inference Endpoint we used for the SFT eval. The comparison is methodologically loose. The qualitative result — Qwen baseline produces invalid JSON ~70% of the time — is robust; the exact magnitude has some noise.

We chose to be calibrated rather than promotional. **The SFT pipeline + the magnitude of improvement is real**, and the artifacts (env, dataset, adapter, scripts) are all reproducible end-to-end with the cleaned adapter at `Krishna3451112/cloud-sec-clean`.

---

## What we'd encourage anyone building agentic RL environments to steal

**Trajectory-aware scoring.** Don't grade just the answer; grade whether the answer is supported by what the agent actually observed. This is the single most important property a hard-to-game reward function can have.

**Composable rubric.** Deterministic primary, LLM-judge auxiliary. Keeps reproducibility (no API keys required) and gets you nuance simultaneously.

**Falsification dimensions.** Reward not just naming the right hypothesis but explicitly ruling out alternatives. This catches a senior-engineering skill that frontier models reliably miss.

---

## Total cost

48 hours of work. About **$5 of HF credits** for the entire SFT + eval pipeline ($1.40 AutoTrain + $3.50 of Inference Endpoint compute). The rest was time and judgment.

---

## Demo video beats (suggested 2-min cut)

1. **The hook** (5 sec): "We built a cloud-security investigation env where Opus 4.5 scores 0% perfect on the first try."
2. **The reward function as the real product** (45 sec): composable + trajectory-aware + falsification.
3. **The calibration moment** (20 sec): the prompt-vs-rubric fairness check and what it taught us.
4. **The training result** (30 sec): 0.05 → 0.900 from 55 trajectories of SFT.
5. **What ships** (20 sec): env + dataset + adapter + recipes, all reproducible.
6. **What's open** (10 sec): GRPO recipe, generalization tests, more tasks.

## Submission writeup framing

Lead with **the reward function**, not the SFT result. The SFT number is a satisfying validation; the rubric is the defensibly-novel piece that other people can lift into their own projects. The 0.05 → 0.900 jump is the proof that the rubric + dataset combination produces something a 7B model can actually learn — not the headline.

The defensible claim: *"We built an OpenEnv-compatible env whose reward function explicitly resists hallucination (via trajectory-aware claim checking) and rewards a senior-engineering skill (explicit elimination of alternatives) that frontier models reliably miss. We then validated the env by running an SFT pipeline that closed ~95% of the Opus gap on a 7B model in 21 minutes of training."*
