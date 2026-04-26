"""Push a proper README.md to the deployed HF Space.

The Space was originally deployed with the auto-generated template README
("A simple test environment that echoes back messages..."). Replace it with
a hackathon-judge-friendly version that links to all assets and shows the
headline result -- while preserving the YAML frontmatter that controls the
Space's docker config.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

SPACE_REPO = "Krishna3451112/cloud-sec-env-space"


SPACE_README = """---
title: PagerBench - Cloud Sec Env
emoji: 🚨
colorFrom: green
colorTo: pink
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
  - cloud-security
  - sre
  - incident-response
  - reward-design
---

# PagerBench — train your agent to investigate, not hallucinate

> An [OpenEnv](https://github.com/meta-pytorch/OpenEnv)-compatible environment where an LLM agent investigates a real-shape cloud-security incident — paged at 2 a.m., 6 tools across 3 clouds, 30 steps to identify the root cause and propose a fix.

> **TL;DR.** The interesting part isn't the task; it's the **reward function**. Our LLM-judge rubric scores answers against the agent's actual investigation trajectory, so an agent that hallucinates the right answer without doing the work scores zero. And it explicitly rewards a senior-SRE skill that frontier models reliably miss: ruling out alternative hypotheses, not just naming the right one. We then validated the env by running an SFT pipeline that took Qwen2.5-7B from **0.05 → 0.900** mean terminal reward — closing ~95% of the gap to Claude Opus.

---

## All project assets

| What | URL |
|---|---|
| **Code (GitHub)** | https://github.com/mohit24bcs10222/cloud-sec-env |
| **SFT training dataset** | https://huggingface.co/datasets/Krishna3451112/cloud-sec-env-sft |
| **Trained adapter (cleaned LoRA)** | https://huggingface.co/Krishna3451112/cloud-sec-clean |
| **Training notebook (Colab one-click)** | https://colab.research.google.com/github/mohit24bcs10222/cloud-sec-env/blob/main/colab/cloud_sec_env_sft.ipynb |
| **Eval notebook (Colab one-click)** | https://colab.research.google.com/github/mohit24bcs10222/cloud-sec-env/blob/main/colab/cloud_sec_env_eval_sft.ipynb |
| **GRPO recipe (env-coupled, runnable)** | https://colab.research.google.com/github/mohit24bcs10222/cloud-sec-env/blob/main/colab/cloud_sec_env_grpo.ipynb |
| **Build journal (every decision + dead end)** | https://github.com/mohit24bcs10222/cloud-sec-env/blob/main/DECISIONS.md |
| **Demo story / video voiceover script** | https://github.com/mohit24bcs10222/cloud-sec-env/blob/main/demo/STORY.md |

---

## Headline numbers

| Model | Submit rate | Mean terminal reward |
|---|---|---|
| Qwen2.5-7B-Instruct (baseline) | ~30% | ~0.05 |
| **Qwen2.5-7B + SFT (LoRA)** | **100%** | **0.900** |
| Claude Opus-4.5 | 100% | 0.96 |

After 21 minutes of SFT on a single A100 (LoRA r=16, 5 epochs, 55 Opus trajectories), Qwen2.5-7B closes ~95% of the gap to Opus on this task.

See [`demo/`](https://github.com/mohit24bcs10222/cloud-sec-env/tree/main/demo) on GitHub for charts: `before_after_chart.png`, `training_loss.png`, `rubric_breakdown.png`, `step_reward_curve.png`.

---

## What the agent sees

The opening alert from `env.reset()`:

```
ALERT  auth_svc_5xx_rate_cloud2
SEV-2  fired 2026-04-22 14:02 UTC
CONDITION  HTTP 5xx rate on auth-svc in cloud-2 > 5% for 30min
CURRENT    8.7%
```

Then 6 tools to use over up to 30 steps:

| Tool | Purpose |
|---|---|
| `logs_search` | Find error patterns scoped to cloud / service / time |
| `trace_get` | Pull the full span tree for one trace_id |
| `metric_query` | Time-series for a named metric (e.g. `sts.jwt_validation_failures`) |
| `ticket_search` | Jira-style change / incident tickets |
| `slack_search` | Engineer chat across 5 channels |
| `kb_search` | Internal knowledge base (some docs are stale on purpose) |

Plus a terminal `submit_answer(root_cause, fix)` action.

---

## Why the reward function is the interesting part

Three claims, each backed by code and measurement:

### 1. Composable — deterministic primary + LLM-judge auxiliary

- **Primary** = deterministic keyword rubric (6 dimensions, binary YES/NO, runs in milliseconds, no API key needed).
- **Auxiliary** = Claude Sonnet LLM judge (9 dimensions, continuous 0-1 with justifications, runs when `ANTHROPIC_API_KEY` is set).

Reproducibility doesn't depend on having an API key. RL training uses fast deterministic rewards. Research-grade eval uses the judge.

### 2. Trajectory-aware — hallucinated answers score zero

The LLM judge receives the agent's full trajectory alongside the submitted answer. For each major claim ("CHG-1891 was applied by j.patel", "cloud-1 is healthy"), the judge checks whether the trajectory contains a tool-call observation that supports it. An agent that emits a perfect answer from system-prompt knowledge — without ever calling the right tools — scores **zero on `evidence_supported_claims`**.

### 3. Falsification-rewarded — what frontier models miss

The `explicit_elimination` dimension rewards naming an alternative hypothesis (CHG-1888) AND ruling it out with a specific reason. Opus consistently identifies the right cause but rarely rules out the alternative; we measured the gap and instrumented it.

---

## Quick API example

```python
import requests

ENV = "https://Krishna3451112-cloud-sec-env-space.hf.space"

# Reset
obs = requests.post(f"{ENV}/reset", json={}).json()["observation"]
print(obs["content"])  # the alert text

# Step
action = {
    "tool_name": "logs_search",
    "arguments": {"cloud": "cloud-2", "service": "auth-svc", "query": "error", "limit": 5},
}
r = requests.post(f"{ENV}/step", json={"action": action}).json()
print("reward:", r["reward"])
print("observation:", r["observation"]["content"])
```

For the full rollout harness + adapters (Anthropic native tool-use + Qwen prompted JSON), see the [GitHub repo](https://github.com/mohit24bcs10222/cloud-sec-env).

---

## What's actually broken (ground truth — agent doesn't see this)

An SRE rotated the OIDC signing key via Terraform two weeks earlier. The apply landed cleanly on cloud-1 and cloud-3 but **silently failed on cloud-2** because another engineer was running a concurrent Terraform plan against cloud-2's state, holding the lock. Cloud-2's sts-broker still has the old public key. New JWTs from Okta fail signature verification on cloud-2 only. Acme tenant routes primarily to cloud-2, so only Acme is paged.

There's also a **tempting wrong hypothesis**: a JWT claim-parser upgrade by the same engineer to the same service one day earlier (CHG-1888). It produces benign WARN logs that look related. The disambiguating insight: it shipped to two clouds, only one of which is broken, so it can't be the cause.

---

## Built for

The Meta-PyTorch / HuggingFace **OpenEnv hackathon, April 2026** (Theme 3 — Professional Tasks / World Modeling). 48 hours, originally a 2-person team that became solo, neither member had fine-tuned an LLM before the event.

## License

BSD 3-Clause (matching OpenEnv).
"""


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN not set in .env", file=sys.stderr)
        return 1

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=SPACE_README.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=SPACE_REPO,
        repo_type="space",
        commit_message="Replace template README with PagerBench landing page (links + numbers)",
    )
    print(f"Pushed README to https://huggingface.co/spaces/{SPACE_REPO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
