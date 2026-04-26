"""Generate the Colab fine-tuning notebook for the PagerBench.

Writes `colab/cloud_sec_env_sft.ipynb` — a self-contained notebook that:
  1. Installs Unsloth + TRL
  2. Downloads our SFT training data (from a URL we'll set after publishing)
  3. Loads Qwen2.5-7B-Instruct in 4-bit
  4. Applies a LoRA adapter
  5. Trains via TRL SFTTrainer
  6. Saves the adapter to /content
  7. Runs a quick inference demo

Run this script to (re)generate the notebook after editing the cell list below.
"""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_TITLE = "PagerBench — SFT fine-tune (Qwen2.5-7B + Unsloth + TRL)"

CELLS: list[tuple[str, str]] = [
    # (cell_type, source)
    (
        "markdown",
        f"""# {NOTEBOOK_TITLE}

This notebook fine-tunes **Qwen2.5-7B-Instruct** on Opus-generated incident-investigation trajectories from our **PagerBench** using [Unsloth](https://github.com/unslothai/unsloth) and [TRL](https://github.com/huggingface/trl).

**Training data:** [Krishna3451112/cloud-sec-env-sft](https://huggingface.co/datasets/Krishna3451112/cloud-sec-env-sft) — 55 high-quality trajectories filtered from Opus-4.5 rollouts (mean terminal reward 0.97 under our deterministic keyword rubric).

**Setup:** Runtime → Change runtime type → **T4 GPU** (free tier works).

**Pipeline:**
1. Install dependencies
2. Load Qwen2.5-7B + LoRA adapter via Unsloth
3. Load and format our SFT dataset
4. Train with TRL's `SFTTrainer`
5. Save adapter + demo inference
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
# Pin TRL to a version that plays well with Unsloth + recent transformers
!pip install --upgrade --force-reinstall --no-deps unsloth
!pip install trl peft accelerate bitsandbytes datasets matplotlib""",
    ),
    (
        "markdown",
        "## 2. Load Qwen2.5-7B-Instruct with 4-bit quantisation + LoRA",
    ),
    (
        "code",
        """from unsloth import FastLanguageModel
import torch

MAX_SEQ_LEN = 4096   # plenty for our trajectory format
DTYPE = None          # auto: bf16 on supported GPUs, else fp16
LOAD_IN_4BIT = True

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-7B-Instruct",  # 4-bit Unsloth variant
    max_seq_length=MAX_SEQ_LEN,
    dtype=DTYPE,
    load_in_4bit=LOAD_IN_4BIT,
)

# Add LoRA adapter -- only ~40M params trainable
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_alpha=16,
    lora_dropout=0.0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=3407,
    use_rslora=False,
    loftq_config=None,
)
print("Model loaded. Trainable params: see Unsloth output above.")""",
    ),
    (
        "markdown",
        """## 3. Load + format the SFT dataset

Our SFT data is one JSONL line per trajectory, each with a `messages` field that's already in chat-template-friendly format.""",
    ),
    (
        "code",
        """from datasets import load_dataset

# Public HF dataset of Opus-generated trajectories from our PagerBench.
# 55 high-quality investigation trajectories, mean terminal reward 0.968.
DATASET_REPO = "Krishna3451112/cloud-sec-env-sft"
dataset = load_dataset(DATASET_REPO, data_files="train.jsonl", split="train")

print(f"Loaded {len(dataset)} training trajectories from {DATASET_REPO}.")
print("Sample first message roles:", [m["role"] for m in dataset[0]["messages"][:6]])

# Cache the system prompt for later inference demo (the .map() call below
# drops the "messages" column).
SYSTEM_PROMPT = dataset[0]["messages"][0]["content"]""",
    ),
    (
        "code",
        """# Apply Qwen's chat template to render messages -> training text.
def format_for_sft(example):
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}

dataset = dataset.map(format_for_sft, remove_columns=[c for c in dataset.column_names if c != "text"])
print("Sample training text (truncated):")
print(dataset[0]["text"][:1500] + "\\n...")
print(f"Mean text length (chars): {sum(len(x['text']) for x in dataset) / len(dataset):.0f}")""",
    ),
    (
        "markdown",
        """## 4. Train with TRL `SFTTrainer`

Conservative defaults for ~30 trajectories. Tune `max_steps` based on dataset size.""",
    ),
    (
        "code",
        """from trl import SFTTrainer, SFTConfig

# Train for ~200 steps -- enough for the model to lock in the JSON output
# format. Earlier we tried ~41 steps and it produced JSON only some of the
# time; 200 reliably lands the format as the dominant mode.
BATCH_SIZE = 1                  # trajectories are long; batch=1 is safe on T4
GRAD_ACCUM_STEPS = 4            # effective batch = 4
TOTAL_EXAMPLES = len(dataset)
MAX_STEPS = 200
print(f"Total examples: {TOTAL_EXAMPLES}; max_steps: {MAX_STEPS}")

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LEN,
    args=SFTConfig(
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM_STEPS,
        warmup_steps=5,
        max_steps=MAX_STEPS,
        learning_rate=2e-4,
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=3407,
        output_dir="/content/cloud_sec_sft_outputs",
        report_to="none",
        save_strategy="no",
    ),
)

trainer_stats = trainer.train()
print("\\nTraining complete.")
print(trainer_stats)""",
    ),
    (
        "code",
        """# Plot training loss
import matplotlib.pyplot as plt

losses = [log["loss"] for log in trainer.state.log_history if "loss" in log]
steps = list(range(1, len(losses) + 1))
plt.figure(figsize=(8, 4))
plt.plot(steps, losses, marker="o", linewidth=1, markersize=3)
plt.xlabel("Training step")
plt.ylabel("Loss")
plt.title("PagerBench -- Qwen2.5-7B SFT loss")
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("/content/sft_loss.png", dpi=120)
plt.show()""",
    ),
    (
        "markdown",
        "## 5. Save adapter + demo inference",
    ),
    (
        "code",
        """# Save LoRA adapter (small file, easy to load post-hoc)
model.save_pretrained("/content/cloud_sec_sft_adapter")
tokenizer.save_pretrained("/content/cloud_sec_sft_adapter")
print("Saved adapter to /content/cloud_sec_sft_adapter")

# Quick inference: feed the alert and see what the fine-tuned model outputs.
FastLanguageModel.for_inference(model)

ALERT = '''ALERT  auth_svc_5xx_rate_cloud2
SEV-2  fired 2026-04-22 14:02 UTC
CONDITION  HTTP 5xx rate on auth-svc in cloud-2 > 5% for 30min
CURRENT    8.7%
RUNBOOK    kb://runbooks/auth-svc-5xx'''

prompt_messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": ALERT},
]
inputs = tokenizer.apply_chat_template(prompt_messages, return_tensors="pt", add_generation_prompt=True).to("cuda")
outputs = model.generate(inputs, max_new_tokens=400, do_sample=True, temperature=0.7)
generated = tokenizer.batch_decode(outputs, skip_special_tokens=False)[0]
print(generated)""",
    ),
    (
        "markdown",
        """## 6. Evaluate the fine-tuned model against the live env

Roll out the trained model against our deployed HF Space env and measure
terminal reward. Compares against the pre-trained Qwen baseline (~0.05 mean).
""",
    ),
    (
        "code",
        """import json, re, requests, time
from collections import Counter

# Live env on HF Spaces. Built from the same code as the local env.
ENV_BASE = "https://Krishna3451112-cloud-sec-env-space.hf.space"

# Sanity ping
try:
    r = requests.post(f"{ENV_BASE}/reset", json={}, timeout=30)
    obs = r.json()["observation"]
    print(f"Env reachable. Initial observation_type: {obs['observation_type']}, steps_remaining: {obs['steps_remaining']}")
except Exception as e:
    print(f"Env unreachable: {e}")
    print("If the Space is still building, wait a minute and retry.")
    raise""",
    ),
    (
        "code",
        '''SYSTEM_PROMPT_FOR_INFERENCE = SYSTEM_PROMPT  # cached from earlier cell

# Robust JSON extractor (mirrors what the QwenAdapter does in our repo).
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

def model_generate(messages, max_new_tokens=512, temperature=0.7):
    inputs = tokenizer.apply_chat_template(messages, return_tensors="pt", add_generation_prompt=True).to("cuda")
    outputs = model.generate(
        inputs,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=temperature,
        pad_token_id=tokenizer.eos_token_id,
    )
    decoded = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
    return decoded

def run_episode(max_steps=30, temperature=0.7, verbose=False):
    """One full rollout against the live HF Space env."""
    r = requests.post(f"{ENV_BASE}/reset", json={}, timeout=60)
    obs = r.json()["observation"]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_FOR_INFERENCE},
        {"role": "user", "content": obs["content"]},
    ]
    total = 0.0
    terminal = None
    submitted = False
    steps_done = 0
    for step in range(max_steps):
        text = model_generate(messages, temperature=temperature)
        parsed = extract_json(text)
        messages.append({"role": "assistant", "content": text})
        if parsed is None or not isinstance(parsed.get("tool_name"), str):
            if verbose: print(f"  step {step+1}: failed to parse JSON; stop")
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
        if verbose: print(f"  step {step+1}: {action_payload[\'tool_name\']} -> reward={reward:.2f}, done={done}")
        messages.append({"role": "user", "content": f"[{new_obs[\'observation_type\'].upper()}]\\n{new_obs[\'content\']}"})
        if done:
            if action_payload["tool_name"] == "submit_answer":
                terminal = reward
                submitted = True
            break
    return {"total_reward": total, "terminal_reward": terminal, "submitted": submitted, "num_steps": steps_done}''',
    ),
    (
        "code",
        """# Switch model into inference mode and run rollouts.
FastLanguageModel.for_inference(model)

N_ROLLOUTS = 5
results = []
for i in range(N_ROLLOUTS):
    print(f"--- Rollout {i+1}/{N_ROLLOUTS} ---")
    res = run_episode(max_steps=30, temperature=0.7, verbose=True)
    results.append(res)
    print(f"  total={res['total_reward']:.3f}, terminal={res['terminal_reward']}, submitted={res['submitted']}, steps={res['num_steps']}")

submitted_terms = [r["terminal_reward"] for r in results if r["terminal_reward"] is not None]
print()
print("=" * 60)
print(f"Fine-tuned Qwen results across {N_ROLLOUTS} rollouts:")
print(f"  Submission rate: {len(submitted_terms)}/{N_ROLLOUTS} = {100*len(submitted_terms)/N_ROLLOUTS:.0f}%")
if submitted_terms:
    print(f"  Mean terminal reward (submitted only): {sum(submitted_terms)/len(submitted_terms):.3f}")
    print(f"  Distribution: min={min(submitted_terms):.2f}, max={max(submitted_terms):.2f}")
print(f"  Mean total reward (all): {sum(r['total_reward'] for r in results)/N_ROLLOUTS:.3f}")
print()
print("Baseline Qwen2.5-7B (pre-SFT) was ~0.05 mean, 20-40% submit rate.")
print("Opus-4.5 ceiling is ~0.96 mean.")""",
    ),
    (
        "code",
        """# Plot before/after distribution
import matplotlib.pyplot as plt
import numpy as np

QWEN_BASELINE = [None, 0.0, 0.0, None, None]  # from our pre-SFT run
QWEN_FINETUNED_TERMS = [r["terminal_reward"] for r in results]
OPUS_TERMS = [1.0, 0.94, 0.97, 1.0, 0.97, 0.85, 0.94, 1.0, 1.0]  # Round-4 sample

def to_finite(xs, fill=0.0):
    return [x if x is not None else fill for x in xs]

groups = ["Qwen baseline", "Qwen + SFT", "Opus 4.5"]
data = [to_finite(QWEN_BASELINE), to_finite(QWEN_FINETUNED_TERMS), OPUS_TERMS]
means = [np.mean(d) if d else 0.0 for d in data]

fig, ax = plt.subplots(figsize=(8, 5))
positions = list(range(len(groups)))
parts = ax.violinplot(data, positions=positions, showmeans=True, widths=0.7)
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
    (
        "markdown",
        """## 7. Save and (optionally) publish the adapter

The trained adapter is in `/content/cloud_sec_sft_adapter`. To use it from outside Colab, push it to HF Hub:""",
    ),
    (
        "code",
        """# Optional: push adapter to HF Hub for downstream eval / sharing.
# Requires you to set HF_TOKEN with write permission.

# import os
# os.environ["HF_TOKEN"] = "<your hf write token>"
# model.push_to_hub("Krishna3451112/cloud-sec-env-qwen-sft", token=os.environ["HF_TOKEN"])
# tokenizer.push_to_hub("Krishna3451112/cloud-sec-env-qwen-sft", token=os.environ["HF_TOKEN"])
# print("Adapter pushed to HF Hub.")""",
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
            "colab": {"name": "cloud_sec_env_sft.ipynb", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
            "accelerator": "GPU",
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


def main() -> int:
    nb = build_notebook(CELLS)
    out = Path(__file__).resolve().parents[1] / "colab" / "cloud_sec_env_sft.ipynb"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    main()
