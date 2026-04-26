# PagerBench: training a 7B model to do on-call investigation, with a reward function that's hard to game

> **TL;DR.** We built an OpenEnv-compatible cloud-security incident-investigation environment, harvested 55 high-quality Opus trajectories, and fine-tuned Qwen2.5-7B via SFT. The interesting part isn't the training — it's the reward function. Our LLM-judge layer scores answers against the agent's actual investigation trajectory, penalizing hallucinated claims. And it rewards a senior-SRE skill that frontier models reliably miss: explicitly ruling out alternative hypotheses, not just naming the right one.
>
> Live env: https://huggingface.co/spaces/Krishna3451112/cloud-sec-env-space
> SFT data: https://huggingface.co/datasets/Krishna3451112/cloud-sec-env-sft
> Trained adapter: https://huggingface.co/Krishna3451112/cloud-sec-clean
> Code: https://github.com/mohit24bcs10222/cloud-sec-env

---

## What's the task?

You're an on-call SRE at a cloud security company. PagerDuty wakes you up:

```
ALERT  auth_svc_5xx_rate_cloud2
SEV-2  fired 2026-04-22 14:02 UTC
CONDITION  HTTP 5xx rate on auth-svc in cloud-2 > 5% for 30min
CURRENT    8.7%
```

You have six tools — `logs_search`, `trace_get`, `metric_query`, `ticket_search`, `slack_search`, `kb_search` — across three clouds and five microservices. You have 30 tool calls. You need to identify the root cause and propose a fix.

The actual cause: an SRE rotated the OIDC signing key via Terraform two weeks earlier. The apply landed cleanly on cloud-1 and cloud-3 but **silently failed on cloud-2** because another engineer was running a concurrent Terraform plan against cloud-2's state, holding the lock. Cloud-2's sts-broker still has the old public key. New JWTs from Okta fail signature verification on cloud-2 only.

It's a real failure mode. State-lock-induced silent Terraform apply failures are a documented production gotcha. So is "only one tenant is affected because of geographic routing."

[image of architecture diagram + alert]

## What makes this env different from card-game RL examples

Most of OpenEnv's reference examples (BlackJack, 2048, Wordle) are single-tool games with well-defined action spaces. They're great for proving GRPO works. They're not so great at testing the kind of skill modern LLMs actually need: **multi-source investigation under uncertainty.**

Our env exposes:

- **Multi-source telemetry**: logs, traces, metrics, tickets, slack, KB docs — all coherent (trace IDs match, timestamps align across signals) but realistically messy (some logs missing trace_ids, service names drift between systems, KB docs go stale).
- **Tempting wrong hypotheses**: a second change ticket (CHG-1888) was applied around the same time by the same engineer to the same service. It produces benign WARN logs that *look* related. The disambiguating insight: it shipped to two clouds, but only one is broken — so it can't be the cause.
- **A 30-step budget**: tight enough that scoping discipline matters. Strong agents finish in ~22 steps; weak ones run out without submitting.

[screenshot showing a single trajectory's tool calls]

## The reward function — three things make it hard to game

This is where we put most of our design effort. The hackathon docs explicitly ask: *"Is hard to game; an agent that exploits the reward without solving the task should not get high scores."*

### 1. Composable: deterministic primary + LLM-judge auxiliary

The **primary reward** is a deterministic keyword-rubric scorer (~6 dimensions, binary YES/NO per dimension, weighted). It runs in milliseconds, has no API dependency, and produces reproducible scores. Judges running our env without an Anthropic key get full primary functionality.

The **auxiliary layer** is a Claude Sonnet-graded rubric that scores nine dimensions on a continuous 0-1 scale with per-dimension justifications. It runs whenever an `ANTHROPIC_API_KEY` is provided — no fallback drama, just opt-in enrichment.

This split was deliberate. **For RL, you need fast deterministic rewards** — LLM judges are too slow and noisy for in-loop training. **For research-grade eval, you want the LLM judge** for nuance. We give you both, layered cleanly.

### 2. Trajectory-aware: hallucinated answers score zero

The biggest novelty is the `evidence_supported_claims` dimension. The judge receives both the agent's submitted answer AND its full trajectory of tool calls + observed results. For each major claim in the answer (like "CHG-1891 was applied by j.patel" or "cloud-1 is healthy"), the judge checks whether *the trajectory contains a tool-call observation that supports it*.

An agent that emits a perfect answer from the system prompt's general knowledge — without ever calling `ticket_search` to find CHG-1891 or `metric_query` to verify cloud-1 is healthy — scores **zero on this dimension**. The reward is grounded in actual investigation, not in surface fluency.

### 3. Falsification-rewarded: explicit elimination of alternatives

The `explicit_elimination` dimension catches what we found frontier models reliably miss. Opus consistently identifies CHG-1891 as the cause. It rarely says *"and CHG-1888 is **not** the cause, because CHG-1888 also shipped to cloud-1, and cloud-1 is healthy."*

That's the senior-SRE move: not just naming a likely culprit, but proving the conclusion against alternatives. Our reward gives 10% weight to this dimension. Without it, perfectly-correct-but-not-rigorous answers cap around 0.90; with it, they hit 1.0.

[example: side-by-side rollout with/without elimination]

## A diagnostic finding worth flagging

While calibrating the env we ran a phase-1 fairness check: was Opus failing `explicit_elimination` because it *can't* do it, or because we *never asked*? We updated the system prompt to explicitly request elimination reasoning and re-ran 5 rollouts. Result: 5/5 hit terminal=1.0.

**The rubric was correct; we'd been penalising Opus for not doing something we never asked.** That's a useful lesson for env-building generally: rubric design and prompt construction are part of the same eval setup.

After re-prompting fairly, we hardened the data instead of the rubric — adding the CHG-1888 competing hypothesis, softening the smoking-gun signals across logs/Slack/tickets — to test investigation rigor rather than instruction-following.

## Training and results

We harvested 30 Opus-4.5 rollouts at temperature 0.7 against the calibrated env. 20 of 30 scored ≥0.85 on the keyword rubric. Combined with high-quality rollouts from prior calibration rounds, we built a dataset of **55 trajectories** (mean terminal reward 0.968, average 24.7 steps each).

Each trajectory got rendered as a chat-template-compatible message list — system prompt + initial alert + alternating `(assistant tool-call JSON, user tool-result)` turns — giving Qwen a clean behavioral-cloning target.

We fine-tuned Qwen2.5-7B-Instruct via Unsloth + TRL's `SFTTrainer` on a free Colab T4. LoRA adapter, 4-bit base model. The full notebook (`cloud_sec_env_sft.ipynb`) trains, plots loss, and evaluates against the live HF Space env in a single run-all.

![Terminal reward by model](before_after_chart.png)

**Baseline → fine-tuned:**
- **Qwen baseline (n=5):** submit rate ~30%, mean terminal ~0.05. Failed JSON parsing dominates the failures. When it does submit, it mentions things like "state lock contention" but vaguely.
- **Qwen + SFT (n=5):** submit rate 100%, mean terminal **0.900**. The model converges on an 18-step investigation that produces the correct CHG-1891 + cloud-2 + state-lock + targeted-reapply diagnosis. Closes ~95% of the gap to Opus.
- **Opus 4.5 ceiling (n=9, calibration round 4):** mean 0.96.

The gap to Opus is ~0.06 absolute, on a rubric where the missing 0.10 is the `avoids_global_rollback` clause — a phrasing trap, not a reasoning gap. The SFT'd 7B model investigates with effectively the same competence as the frontier teacher on this task.

**What the model learned:**
- The output format (JSON tool-calls vs. broken prose)
- Search keywords that work (e.g. searching tickets for "OIDC" + "rotation" rather than "STS broker configuration")
- When to pivot from logs to traces
- When to read Slack vs. when to keep searching tickets

## Things we explicitly chose not to do

- **No GRPO yet.** Our research showed every successful OpenEnv RL example to date is on much simpler tasks (BlackJack, Wordle, 2048). LinkedIn's GPT-OSS multi-tool RL retro used 16 H100 nodes and ran for days, with multiple silent failure modes (MoE log-prob mismatches, FA2/FA3 attention-sink kernel bugs). That's not a hackathon-timeline experiment. SFT first; GRPO is documented as the natural follow-up in our Colab notebook.
- **No simulator.** Hand-authored data forces realism judgment that simulator code wouldn't develop.
- **No live env.** Frozen snapshot per task. Live state would 5x the engineering scope without changing the investigation skills under test.

## Try it

- **Live env**: open the [HF Space](https://huggingface.co/spaces/Krishna3451112/cloud-sec-env-space). The web interface lets you click through actions manually.
- **Reproduce baseline**: `pip install openenv-core` then point an `EnvClient` at the Space URL.
- **Fine-tune**: open `cloud_sec_env_sft.ipynb` in Colab, set runtime to T4, hit Run All. Self-contained.
- **Code**: https://github.com/mohit24bcs10222/cloud-sec-env

## What's next

The env is ready for a second task. Most of the infrastructure (rubric scorer, LLM judge prompt, harness, adapters, Colab notebook) is reusable as-is. Adding a second incident type (e.g., a network-policy bug) is mostly data-authoring + a fresh ground-truth + a few rubric-prompt edits. The same training pipeline should work.

If you're building agentic RL environments, two things from this project we'd encourage you to steal:

1. **Trajectory-aware scoring.** Don't grade just the answer; grade whether the answer is supported by what the agent actually observed.
2. **Composable rubric.** Deterministic primary, LLM-judge auxiliary. Keeps reproducibility and gets you nuanced eval simultaneously.

---

## Acknowledgements

Built in 48h for the OpenEnv hackathon. Thanks to Meta-PyTorch, HuggingFace, and the Unsloth team for making the framework accessible to two engineers new to fine-tuning.

---

## Appendix: rubric in detail (for the curious)

**Primary keyword rubric** (deterministic, 6 dimensions, weights sum to 1.0):
- `identify_chg_1891` (0.25): mentions both CHG-1891 and j.patel
- `identify_cloud2_scope` (0.15): scopes to cloud-2 with awareness of cloud-1 / cloud-3 health
- `identify_state_lock_mechanism` (0.20): names "state lock" + (m.chen | concurrent)
- `identify_stale_key_symptom` (0.15): connects sig-verification failure + rotation context
- `proposes_targeted_reapply` (0.15): targeted re-apply mentioning cloud-2
- `avoids_global_rollback` (0.10): doesn't recommend a global rollback

**Auxiliary LLM-judge rubric** (continuous, 9 dimensions including the above + `explicit_elimination` + `evidence_supported_claims` + `cites_specific_evidence`).

**Step-level signals** (additive, applied during the episode):
- +0.10 each: correct first tool, finds signature error, finds CHG-1891 ticket, reads state-lock Slack, finds correct runbook
- +0.05: pivots from log to trace using a real trace_id observed earlier
- −0.05 per occurrence: `logs_search` without scoping
- −0.10 once: 3+ consecutive cloud-3-scoped calls (red-herring fixation)

Per-step rewards give RL training a dense gradient even before the model can reach `submit_answer`.
