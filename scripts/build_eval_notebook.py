"""Generate the eval-only Colab notebook.

Writes `colab/cloud_sec_env_eval.ipynb` -- a notebook that:
  1. Asks the user to upload `cloud_sec_adapter.zip`
  2. Unzips + loads base Qwen2.5-7B + LoRA adapter via Unsloth
  3. Pings the deployed HF Space env
  4. Runs N rollouts at greedy decoding (do_sample=False)
  5. Plots before/after distribution

No training. Skip-the-50-min-fine-tune flow.
"""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_TITLE = "PagerBench -- Evaluate fine-tuned Qwen (no retrain)"

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        f"""# {NOTEBOOK_TITLE}

This notebook evaluates an **already-trained** Qwen2.5-7B + LoRA adapter against the live [PagerBench HF Space](https://huggingface.co/spaces/Krishna3451112/cloud-sec-env-space). No training step.

**Setup:** Runtime -> Change runtime type -> **T4 GPU** (free tier works).

**You need:** the `cloud_sec_adapter.zip` file you downloaded after fine-tuning. Upload it to `/content` via the Files pane on the left BEFORE running cell 2.

**Pipeline:**
1. Install dependencies
2. Unzip the adapter (you upload the zip first)
3. Load Qwen2.5-7B base + your LoRA adapter
4. Define eval helpers + ping the live env
5. Run 5 rollouts with greedy decoding
6. Plot before/after vs Opus
""",
    ),
    (
        "markdown",
        "## 1. Install dependencies",
    ),
    (
        "code",
        """%%capture
!pip install unsloth
!pip install --upgrade --force-reinstall --no-deps unsloth
!pip install peft accelerate bitsandbytes requests matplotlib""",
    ),
    (
        "markdown",
        """## 2. Upload your adapter zip to `/content`

Drag-and-drop `cloud_sec_adapter.zip` into the Files pane on the left, then run this cell to unzip it.""",
    ),
    (
        "code",
        """import os
from pathlib import Path

ADAPTER_ZIP = "/content/cloud_sec_adapter.zip"
ADAPTER_DIR = "/content/cloud_sec_sft_adapter"

if not Path(ADAPTER_ZIP).exists():
    raise FileNotFoundError(
        f"Upload cloud_sec_adapter.zip to /content first (drag-drop in the Files pane on the left). "
        f"Expected at {ADAPTER_ZIP}."
    )

# Unzip if not already extracted
if not Path(ADAPTER_DIR).exists():
    !cd /content && unzip -q -o cloud_sec_adapter.zip
    # The zip might extract to a nested path -- normalize.
    candidates = [
        ADAPTER_DIR,
        "/content/content/cloud_sec_sft_adapter",
    ]
    for c in candidates:
        if Path(c).exists() and (Path(c) / "adapter_config.json").exists():
            if c != ADAPTER_DIR:
                !mv {c} {ADAPTER_DIR}
            break

assert (Path(ADAPTER_DIR) / "adapter_config.json").exists(), (
    f"Couldn't find adapter_config.json under {ADAPTER_DIR}. List of /content:\\n"
    + "\\n".join(p.name for p in Path("/content").iterdir())
)
print(f"Adapter ready at {ADAPTER_DIR}")
print("Files:", [p.name for p in Path(ADAPTER_DIR).iterdir()])""",
    ),
    (
        "markdown",
        """## 3. Load Qwen2.5-7B base + your LoRA adapter

Unsloth auto-detects the base model from `adapter_config.json` and loads it in 4-bit, then applies your adapter.""",
    ),
    (
        "code",
        """from unsloth import FastLanguageModel
import torch

MAX_SEQ_LEN = 4096
ADAPTER_DIR = "/content/cloud_sec_sft_adapter"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=ADAPTER_DIR,
    max_seq_length=MAX_SEQ_LEN,
    dtype=None,
    load_in_4bit=True,
)
FastLanguageModel.for_inference(model)

print("Model + adapter loaded.")
print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only'}")""",
    ),
    (
        "markdown",
        """## 4. Define eval helpers + ping the live env""",
    ),
    (
        "code",
        """import json, re, requests
from collections import Counter

ENV_BASE = "https://Krishna3451112-cloud-sec-env-space.hf.space"

# Sanity ping
r = requests.post(f"{ENV_BASE}/reset", json={}, timeout=60)
obs = r.json()["observation"]
print(f"Env reachable. observation_type: {obs['observation_type']}, steps_remaining: {obs['steps_remaining']}")
print(f"Initial alert (preview): {obs['content'][:120]}...")""",
    ),
    (
        "code",
        """SYSTEM_PROMPT = '''You are an on-call Site Reliability Engineer (SRE) at NimbusGuard, a cloud-security SaaS.

You've been paged with an incident alert. Investigate using the tools available, identify the root cause, and propose a fix.

**Environment:** 3 cloud deployments (cloud-1 us-east, cloud-2 us-west, cloud-3 eu-west). Core services per cloud: api-gateway, auth-svc, sts-broker, policy-svc, audit-logger. Customers federate identity via OIDC.

**Budget:** 30 tool calls maximum.

**When you submit_answer, provide:**
- root_cause: what actually broke and why. A senior SRE proves their conclusion against alternatives, so identify the most plausible alternative hypothesis your investigation surfaced and explain why it isn't the cause.
- fix: the specific remediation.
'''


def extract_json(text):
    if not text: return None
    text = text.strip()
    if text.startswith("```"):
        nl = text.find("\\n")
        if nl >= 0: text = text[nl+1:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict): return obj
    except Exception: pass
    start = text.find("{")
    if start < 0: return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i+1])
                    if isinstance(obj, dict): return obj
                except Exception: return None
                break
    return None


def model_generate(messages, max_new_tokens=512, do_sample=False, temperature=0.1):
    inputs = tokenizer.apply_chat_template(
        messages, return_tensors="pt", add_generation_prompt=True
    ).to("cuda")
    gen_kwargs = dict(
        max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.eos_token_id,
    )
    if do_sample:
        gen_kwargs["do_sample"] = True
        gen_kwargs["temperature"] = temperature
        gen_kwargs["top_p"] = 0.9
    else:
        gen_kwargs["do_sample"] = False
    outputs = model.generate(inputs, **gen_kwargs)
    return tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)


def run_episode(max_steps=30, do_sample=False, temperature=0.1, verbose=True):
    r = requests.post(f"{ENV_BASE}/reset", json={}, timeout=60)
    obs = r.json()["observation"]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": obs["content"]},
    ]
    total = 0.0
    terminal = None
    submitted = False
    steps_done = 0
    parse_failures = 0
    for step in range(max_steps):
        text = model_generate(messages, do_sample=do_sample, temperature=temperature)
        parsed = extract_json(text)
        messages.append({"role": "assistant", "content": text})
        if parsed is None or not isinstance(parsed.get("tool_name"), str):
            parse_failures += 1
            if verbose:
                print(f"  step {step+1}: failed to parse JSON; raw: {text[:160]!r}")
            break
        action_payload = {
            "tool_name": parsed["tool_name"],
            "arguments": parsed.get("arguments") or {},
            "reasoning": parsed.get("reasoning"),
        }
        try:
            r = requests.post(f"{ENV_BASE}/step", json={"action": action_payload}, timeout=120)
            payload = r.json()
        except Exception as e:
            if verbose: print(f"  step {step+1}: env call failed: {e}")
            break
        new_obs = payload["observation"]
        reward = payload.get("reward") or 0.0
        total += reward
        done = payload.get("done", False)
        steps_done = step + 1
        if verbose:
            print(f"  step {step+1}: {action_payload['tool_name']} -> reward={reward:.2f}, done={done}")
        messages.append(
            {"role": "user", "content": f"[{new_obs['observation_type'].upper()}]\\n{new_obs['content']}"}
        )
        if done:
            if action_payload["tool_name"] == "submit_answer":
                terminal = reward
                submitted = True
            break
    return {
        "total_reward": total, "terminal_reward": terminal,
        "submitted": submitted, "num_steps": steps_done,
        "parse_failures": parse_failures,
    }""",
    ),
    (
        "markdown",
        """## 5. Run 5 rollouts (greedy decoding)

Greedy = the model picks its highest-probability token each step. Removes sampling variance and is the most reliable way to elicit the JSON-format behavior the model learned during fine-tuning.""",
    ),
    (
        "code",
        """N_ROLLOUTS = 5
results = []
for i in range(N_ROLLOUTS):
    print(f"--- Rollout {i+1}/{N_ROLLOUTS} (greedy) ---")
    res = run_episode(do_sample=False)
    results.append(res)
    print(
        f"  total={res['total_reward']:.3f}, terminal={res['terminal_reward']}, "
        f"submitted={res['submitted']}, steps={res['num_steps']}, "
        f"parse_failures={res['parse_failures']}"
    )

submitted_terms = [r["terminal_reward"] for r in results if r["terminal_reward"] is not None]
parse_failures_total = sum(r["parse_failures"] for r in results)

print()
print("=" * 60)
print(f"Fine-tuned Qwen across {N_ROLLOUTS} rollouts (greedy decoding):")
print(f"  Submission rate: {len(submitted_terms)}/{N_ROLLOUTS} = {100*len(submitted_terms)/N_ROLLOUTS:.0f}%")
if submitted_terms:
    print(f"  Mean terminal reward (submitted only): {sum(submitted_terms)/len(submitted_terms):.3f}")
    print(f"  Distribution: min={min(submitted_terms):.2f}, max={max(submitted_terms):.2f}")
print(f"  Mean total reward (all): {sum(r['total_reward'] for r in results)/N_ROLLOUTS:.3f}")
print(f"  Total parse failures: {parse_failures_total}")
print()
print("Reference: Qwen baseline = ~0.05 mean (rarely submits). Opus 4.5 ceiling = ~0.96.")""",
    ),
    (
        "markdown",
        """## (Optional) If greedy still parse-fails, try low-temp sampling

If you saw `parse_failures` near 5, the model didn't lock in JSON during fine-tuning. Run this cell as a fallback -- low-temp sampling (`temperature=0.1`) sometimes finds the JSON path even when greedy doesn't.""",
    ),
    (
        "code",
        """# Optional fallback -- only run if greedy failed
if sum(r["parse_failures"] for r in results) >= N_ROLLOUTS:
    print("Greedy produced parse failures. Retrying with temperature=0.1 sampling...")
    results = []
    for i in range(N_ROLLOUTS):
        print(f"--- Rollout {i+1}/{N_ROLLOUTS} (temp=0.1) ---")
        res = run_episode(do_sample=True, temperature=0.1)
        results.append(res)
        print(
            f"  total={res['total_reward']:.3f}, terminal={res['terminal_reward']}, "
            f"submitted={res['submitted']}, steps={res['num_steps']}, "
            f"parse_failures={res['parse_failures']}"
        )
    submitted_terms = [r["terminal_reward"] for r in results if r["terminal_reward"] is not None]
    print()
    print(f"With temp=0.1: submission rate {len(submitted_terms)}/{N_ROLLOUTS}, "
          f"mean terminal: {sum(submitted_terms)/len(submitted_terms):.3f}" if submitted_terms else "no submissions")
else:
    print("Greedy already produced submissions; skipping fallback.")""",
    ),
    (
        "markdown",
        "## 6. Before/after violin chart",
    ),
    (
        "code",
        """import matplotlib.pyplot as plt
import numpy as np

QWEN_BASELINE = [0.0, 0.0, 0.0, 0.0, 0.0]   # baseline rarely submits; treated as 0
QWEN_FINETUNED_TERMS = [
    r["terminal_reward"] if r["terminal_reward"] is not None else 0.0
    for r in results
]
OPUS_TERMS = [1.0, 0.94, 0.97, 1.0, 0.97, 0.85, 0.94, 1.0, 1.0]   # measured Round-4

groups = ["Qwen baseline", "Qwen + SFT", "Opus 4.5"]
data = [QWEN_BASELINE, QWEN_FINETUNED_TERMS, OPUS_TERMS]
means = [np.mean(d) for d in data]

fig, ax = plt.subplots(figsize=(8, 5))
positions = list(range(len(groups)))
ax.violinplot(data, positions=positions, showmeans=True, widths=0.7)
ax.set_xticks(positions)
ax.set_xticklabels(groups)
ax.set_ylabel("Terminal reward")
ax.set_title("PagerBench: terminal reward by model")
ax.set_ylim(-0.05, 1.05)
ax.grid(True, alpha=0.3)
for i, m in enumerate(means):
    ax.annotate(f"mean={m:.2f}", xy=(i, m), xytext=(i, m + 0.05),
                ha="center", fontsize=10, fontweight="bold")
plt.tight_layout()
plt.savefig("/content/before_after_curve.png", dpi=130)
plt.show()
print("Saved /content/before_after_curve.png")""",
    ),
]


def build_notebook(cells: list[tuple[str, str]]) -> dict:
    nb_cells = []
    for cell_type, source in cells:
        nb_cell = {
            "cell_type": cell_type,
            "metadata": {},
            "source": source.splitlines(keepends=True) if "\n" in source else [source],
        }
        if cell_type == "code":
            nb_cell["execution_count"] = None
            nb_cell["outputs"] = []
        nb_cells.append(nb_cell)

    return {
        "cells": nb_cells,
        "metadata": {
            "colab": {"name": "cloud_sec_env_eval.ipynb", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
            "accelerator": "GPU",
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


def main() -> int:
    nb = build_notebook(CELLS)
    out = Path(__file__).resolve().parents[1] / "colab" / "cloud_sec_env_eval.ipynb"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    main()
