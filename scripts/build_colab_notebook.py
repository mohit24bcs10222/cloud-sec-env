"""Generate the Colab fine-tuning notebook for the Cloud Sec Env.

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

NOTEBOOK_TITLE = "Cloud Sec Env — SFT fine-tune (Qwen2.5-7B + Unsloth + TRL)"

CELLS: list[tuple[str, str]] = [
    # (cell_type, source)
    (
        "markdown",
        f"""# {NOTEBOOK_TITLE}

This notebook fine-tunes **Qwen2.5-7B-Instruct** on Opus-generated incident-investigation trajectories from our [Cloud Sec Env](https://github.com/<TODO-repo>) using [Unsloth](https://github.com/unslothai/unsloth) and [TRL](https://github.com/huggingface/trl).

**Setup:** Runtime → Change runtime type → **T4 GPU** (free tier works).

**What this does in 5 cells:**
1. Install dependencies
2. Load Qwen2.5-7B + LoRA adapter via Unsloth
3. Load and format our SFT dataset (Opus trajectories)
4. Train with TRL's `SFTTrainer`
5. Demo inference + save adapter
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
from pathlib import Path

# Option A -- load from a HF dataset (fill in once published):
#   dataset = load_dataset("<your-username>/cloud-sec-env-sft", split="train")
#
# Option B -- upload `cloud_sec_train.jsonl` to /content via the file pane,
# or pull from a raw URL:
DATA_URL = "https://raw.githubusercontent.com/<TODO-user>/<TODO-repo>/main/data/sft/cloud_sec_train.jsonl"
DATA_LOCAL = Path("/content/cloud_sec_train.jsonl")

if not DATA_LOCAL.exists():
    !wget -q -O /content/cloud_sec_train.jsonl $DATA_URL || echo "(falling back to local upload)"

dataset = load_dataset("json", data_files=str(DATA_LOCAL), split="train")
print(f"Loaded {len(dataset)} training trajectories.")
print("Sample first message roles:", [m["role"] for m in dataset[0]["messages"][:6]])""",
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

# Compute a reasonable step count. Each example is one full trajectory; we
# do ~3 epochs over the dataset.
NUM_EPOCHS = 3
BATCH_SIZE = 1                  # trajectories are long; batch=1 is safe on T4
GRAD_ACCUM_STEPS = 4            # effective batch = 4
TOTAL_EXAMPLES = len(dataset)
MAX_STEPS = max(20, (NUM_EPOCHS * TOTAL_EXAMPLES) // (BATCH_SIZE * GRAD_ACCUM_STEPS))
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
plt.title("Cloud Sec Env -- Qwen2.5-7B SFT loss")
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

# Pull the same system prompt our env adapter uses.
import urllib.request, json
SYSTEM_PROMPT_URL = "https://raw.githubusercontent.com/<TODO-user>/<TODO-repo>/main/cloud_sec_env/agent/tool_specs.py"
# (For the demo we just inline a short stub; the real fine-tune already saw the full prompt)
SHORT_SYSTEM = "You are an on-call SRE. Investigate the alert using the available tools and respond with a JSON action object."

prompt_messages = [
    {"role": "system", "content": SHORT_SYSTEM},
    {"role": "user", "content": ALERT},
]
inputs = tokenizer.apply_chat_template(prompt_messages, return_tensors="pt", add_generation_prompt=True).to("cuda")
outputs = model.generate(inputs, max_new_tokens=400, do_sample=True, temperature=0.7)
print(tokenizer.batch_decode(outputs, skip_special_tokens=False)[0])""",
    ),
    (
        "markdown",
        """## Next steps after this notebook

- Connect to the running env (HF Space) and roll out a few episodes with this adapter loaded
- Compare to the pre-fine-tune baseline (~0.05 mean) and Opus (~0.96 mean) to plot the curve
- (Optional) Push the adapter to HF Hub: `model.push_to_hub("<your-username>/cloud-sec-env-qwen-sft")`""",
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
