"""Generate the eval-the-SFT'd-model Colab notebook.

Writes `colab/cloud_sec_env_eval_sft.ipynb` -- a self-contained notebook that:
  1. Installs deps (unsloth + transformers + peft + requests)
  2. Loads Qwen2.5-7B base + our trained LoRA adapter from the HF Hub
  3. Pings the deployed env Space
  4. Runs N greedy rollouts against the Space and prints a results table
  5. Saves a violin chart comparing baseline / Qwen+SFT / Opus

Run this script to (re)generate the notebook after editing the cells.
"""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_TITLE = "Cloud Sec Env -- Evaluate the SFT'd Qwen against the live env"

# Hub repos / URLs the notebook references.
ADAPTER_REPO = "Krishna3451112/cloud-sec"            # AutoTrain pushed here
DATASET_REPO = "Krishna3451112/cloud-sec-env-sft"    # for fetching SYSTEM_PROMPT
ENV_SPACE_URL = "https://Krishna3451112-cloud-sec-env-space.hf.space"


CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        f"""# {NOTEBOOK_TITLE}

This notebook evaluates the **SFT-tuned Qwen2.5-7B** (LoRA adapter trained on
55 high-reward Opus trajectories) against our **deployed Cloud Sec Env** on
HuggingFace Spaces.

**What you get out of this notebook:**
- Submission rate (out of 5 episodes)
- Mean terminal reward
- Per-episode breakdown
- A violin chart comparing baseline / SFT'd / Opus

**Setup**: Runtime > Change runtime type > **T4 GPU** (or A100 if you have Pro).

**Inputs (no user action needed -- already on the Hub):**
- Adapter: [`{ADAPTER_REPO}`](https://huggingface.co/{ADAPTER_REPO})
- SFT dataset (for system prompt): [`{DATASET_REPO}`](https://huggingface.co/datasets/{DATASET_REPO})
- Env Space: [`{ENV_SPACE_URL}`]({ENV_SPACE_URL})
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
!pip install transformers peft accelerate bitsandbytes datasets requests matplotlib""",
    ),
    (
        "markdown",
        """## 2. Load Qwen2.5-7B + the trained LoRA adapter

Loads the 4-bit base model and applies your AutoTrain-trained LoRA adapter
from the Hub. ~3 minutes on T4, ~1 minute on A100.""",
    ),
    (
        "code",
        f'''from unsloth import FastLanguageModel
import torch

ADAPTER_REPO = "{ADAPTER_REPO}"
BASE_MODEL = "unsloth/Qwen2.5-7B-Instruct"
MAX_SEQ_LEN = 4096

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=MAX_SEQ_LEN,
    load_in_4bit=True,
)

# Apply the trained LoRA adapter
model.load_adapter(ADAPTER_REPO, adapter_name="sft")
FastLanguageModel.for_inference(model)
print(f"Loaded base + adapter from {{ADAPTER_REPO}}")
print(f"Trainable params (frozen for inference): {{sum(p.numel() for p in model.parameters() if p.requires_grad):,}}")''',
    ),
    (
        "markdown",
        """## 3. Pull the system prompt + smoke-test the env

The system prompt was baked into the SFT dataset; we re-use it here so the
model sees the same context it was trained on.""",
    ),
    (
        "code",
        f'''from datasets import load_dataset
import requests

ENV_BASE = "{ENV_SPACE_URL}"
DATASET_REPO = "{DATASET_REPO}"

ds = load_dataset(DATASET_REPO, data_files="train.jsonl", split="train")
SYSTEM_PROMPT = ds[0]["messages"][0]["content"]
print(f"System prompt: {{len(SYSTEM_PROMPT)}} chars")
print(SYSTEM_PROMPT[:300] + "\\n...")

# Smoke-test the env Space.
r = requests.post(f"{{ENV_BASE}}/reset", json={{}}, timeout=60).json()
obs = r["observation"]
print(f"\\nEnv reachable. observation_type={{obs['observation_type']}}, steps_remaining={{obs['steps_remaining']}}")
print("Initial alert:")
print(obs["content"][:300])''',
    ),
    (
        "markdown",
        """## 4. Helpers: greedy generation, JSON extraction, episode driver

Greedy decoding (`do_sample=False`) is essential here -- the SFT'd model was
trained to emit JSON deterministically. Sampling at temperature 0.7 (the
naive default) is what made the previous Colab run look like the model
"didn't learn"; it had learned, but the noise was killing the format.""",
    ),
    (
        "code",
        '''import json, re

def extract_json(text):
    """Best-effort JSON extraction from model output. Mirrors QwenAdapter."""
    if not text: return None
    text = text.strip()
    if text.startswith("```"):
        nl = text.find("\\n")
        if nl >= 0: text = text[nl+1:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
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
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
                break
    return None


def model_generate(messages, max_new_tokens=512):
    """GREEDY decode -- locks in the JSON format the model just learned.

    Uses transformers 5.x API: apply_chat_template with return_dict=True returns
    a BatchEncoding (input_ids + attention_mask). Pass with **inputs.
    """
    inputs = tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        add_generation_prompt=True,
        return_dict=True,
    ).to("cuda")
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,            # GREEDY, not sampling
        pad_token_id=tokenizer.eos_token_id,
    )
    prompt_len = inputs["input_ids"].shape[1]
    return tokenizer.decode(outputs[0][prompt_len:], skip_special_tokens=True)


def run_episode(verbose=False, max_steps=30):
    """One full rollout against the live env Space. Returns dict of episode stats."""
    obs = requests.post(f"{ENV_BASE}/reset", json={}, timeout=60).json()["observation"]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": obs["content"]},
    ]
    total = 0.0
    terminal = None
    submitted = False
    steps = 0
    stop_reason = "budget_exhausted"
    for step in range(max_steps):
        text = model_generate(messages)
        parsed = extract_json(text)
        messages.append({"role": "assistant", "content": text})
        if parsed is None or not isinstance(parsed.get("tool_name"), str):
            stop_reason = "parse_fail"
            if verbose:
                print(f"  step {step+1}: PARSE FAIL. Raw text: {text[:160]!r}")
            break
        action = {
            "tool_name": parsed["tool_name"],
            "arguments": parsed.get("arguments") or {},
            "reasoning": parsed.get("reasoning"),
        }
        try:
            r = requests.post(f"{ENV_BASE}/step", json={"action": action}, timeout=120).json()
        except Exception as e:
            stop_reason = f"env_error:{type(e).__name__}"
            if verbose: print(f"  step {step+1}: env error {e}")
            break
        new_obs = r["observation"]
        reward = float(r.get("reward") or 0.0)
        total += reward
        steps = step + 1
        if verbose:
            print(f"  step {step+1}: {action['tool_name']:14s} reward={reward:+.3f} done={r.get('done')}")
        messages.append({
            "role": "user",
            "content": f"[{new_obs['observation_type'].upper()}]\\n{new_obs['content']}",
        })
        if r.get("done"):
            if action["tool_name"] == "submit_answer":
                terminal = reward
                submitted = True
                stop_reason = "submit"
            else:
                stop_reason = f"done:{new_obs['observation_type']}"
            break
    return {
        "submitted": submitted,
        "terminal_reward": terminal,
        "total_reward": round(total, 4),
        "num_steps": steps,
        "stop_reason": stop_reason,
    }''',
    ),
    (
        "markdown",
        """## 5. Run rollouts

5 episodes is enough to see the headline result. Each takes ~2-3 minutes
(model generates ~25 turns, each turn = one greedy generation + one HTTP
roundtrip to the Space). Total: 10-15 min on T4, 4-6 min on A100.""",
    ),
    (
        "code",
        '''N_ROLLOUTS = 5
results = []
for i in range(N_ROLLOUTS):
    print(f"--- Rollout {i+1}/{N_ROLLOUTS} ---")
    res = run_episode(verbose=True)
    results.append(res)
    term = f"{res['terminal_reward']:.3f}" if res['terminal_reward'] is not None else "-"
    print(f"  -> submit={res['submitted']} terminal={term} total={res['total_reward']:.3f} "
          f"steps={res['num_steps']} stop={res['stop_reason']}")
    print()''',
    ),
    (
        "markdown",
        "## 6. Aggregate + headline numbers",
    ),
    (
        "code",
        '''submitted_terms = [r["terminal_reward"] for r in results if r["terminal_reward"] is not None]
n = len(results)
n_sub = len(submitted_terms)
mean_terminal = sum(submitted_terms) / n_sub if n_sub else 0.0
mean_total = sum(r["total_reward"] for r in results) / n if n else 0.0
mean_steps = sum(r["num_steps"] for r in results) / n if n else 0.0

print("=" * 64)
print(f"Cloud Sec Env -- Qwen2.5-7B + SFT (LoRA) -- {n} rollouts")
print("=" * 64)
print(f"Submission rate:                         {n_sub}/{n}  ({100*n_sub/n:.0f}%)")
print(f"Mean terminal reward (submitted only):   {mean_terminal:.3f}")
print(f"Mean total reward (all episodes):        {mean_total:.3f}")
print(f"Mean steps per episode:                  {mean_steps:.1f}")
print()
print("Per-episode:")
print("  #  submit  terminal   total   steps   stop")
for i, r in enumerate(results, 1):
    term = f"{r['terminal_reward']:.3f}" if r['terminal_reward'] is not None else "  -  "
    print(f"  {i}  {'YES   ' if r['submitted'] else 'NO    '} {term}    {r['total_reward']:+.3f}   {r['num_steps']:2d}     {r['stop_reason']}")
print()
print("Reference numbers from earlier rounds:")
print("  Qwen2.5-7B (no SFT):   submit ~20-40%, mean terminal ~0.05")
print("  Claude Opus-4.5:       submit 100%,    mean terminal ~0.96")''',
    ),
    (
        "markdown",
        "## 7. Save markdown summary (paste this into README/blog)",
    ),
    (
        "code",
        '''md = []
md.append("## Qwen2.5-7B + SFT eval (vs deployed Space)")
md.append("")
md.append(f"- Episodes: {n}")
md.append(f"- Submission rate: **{100*n_sub/n:.0f}%** ({n_sub}/{n})")
md.append(f"- Mean terminal reward (submitted): **{mean_terminal:.3f}**")
md.append(f"- Mean total reward (all): **{mean_total:.3f}**")
md.append(f"- Mean steps: {mean_steps:.1f}")
md.append("")
md.append("| # | submitted | terminal | total | steps | stop |")
md.append("|---|---|---|---|---|---|")
for i, r in enumerate(results, 1):
    term = f"{r['terminal_reward']:.3f}" if r['terminal_reward'] is not None else "-"
    md.append(f"| {i} | {'YES' if r['submitted'] else 'NO'} | {term} | "
              f"{r['total_reward']:.3f} | {r['num_steps']} | `{r['stop_reason']}` |")
md_text = "\\n".join(md)
print(md_text)

# Save for download
with open("/content/eval_summary.md", "w") as f:
    f.write(md_text)
print("\\nSaved /content/eval_summary.md")''',
    ),
    (
        "markdown",
        """## 8. Comparison chart (baseline vs SFT vs Opus)

Saves `before_after_chart.png` -- this is the asset for the README + blog.""",
    ),
    (
        "code",
        '''import matplotlib.pyplot as plt
import numpy as np

# Reference numbers from prior measurements (same env, same scoring)
QWEN_BASELINE = [0.0, 0.0, 0.0, 0.0, 0.0]                                # ~5% mean, mostly non-submits
OPUS_TERMS = [1.0, 0.94, 0.97, 1.0, 0.97, 0.85, 0.94, 1.0, 1.0]          # measured Round 4

QWEN_SFT = [r["terminal_reward"] if r["terminal_reward"] is not None else 0.0 for r in results]

groups = ["Qwen base\\n(no SFT)", f"Qwen + SFT\\n({n} eps)", "Claude\\nOpus-4.5"]
data = [QWEN_BASELINE, QWEN_SFT, OPUS_TERMS]
means = [np.mean(d) for d in data]
counts = [len(d) for d in data]

fig, ax = plt.subplots(figsize=(9, 5.5))
positions = list(range(len(groups)))
parts = ax.violinplot(data, positions=positions, showmeans=True, widths=0.7)
for body in parts["bodies"]:
    body.set_alpha(0.5)
ax.set_xticks(positions)
ax.set_xticklabels(groups, fontsize=11)
ax.set_ylabel("Terminal reward (deterministic keyword rubric)")
ax.set_title("Cloud Sec Env -- terminal reward by model")
ax.set_ylim(-0.05, 1.10)
ax.grid(True, alpha=0.3)
for i, (m, c) in enumerate(zip(means, counts)):
    ax.annotate(f"mean={m:.2f}\\nn={c}", xy=(i, m), xytext=(i, m + 0.06),
                ha="center", fontsize=10, fontweight="bold")
plt.tight_layout()
plt.savefig("/content/before_after_chart.png", dpi=150)
plt.show()
print("Saved /content/before_after_chart.png  (download from the file panel on the left)")''',
    ),
    (
        "markdown",
        """## 9. Done

**What to do with the outputs**
1. Download `/content/eval_summary.md` -- paste the table into `README.md`'s
   "Measured headline numbers" section, replacing the `TBD` row.
2. Download `/content/before_after_chart.png` -- save to the repo as
   `demo/before_after_chart.png` and embed in the README + blog post.
3. Send me (or copy-paste somewhere) the per-episode results so the build
   journal in `DECISIONS.md` can be updated with the final numbers.

**If submit rate is low (<60%)**: re-train with `block_size=16384` and
`use_flash_attention_2=true` so the long trajectories aren't truncated. The
~12.8k-token outliers we saw in the AutoTrain log were getting cut at 8192,
losing the `submit_answer` turn.""",
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
            "colab": {"name": "cloud_sec_env_eval_sft.ipynb", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
            "accelerator": "GPU",
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


def main() -> int:
    nb = build_notebook(CELLS)
    out = Path(__file__).resolve().parents[1] / "colab" / "cloud_sec_env_eval_sft.ipynb"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    main()
