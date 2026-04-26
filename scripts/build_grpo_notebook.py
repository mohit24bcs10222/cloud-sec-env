"""Generate the GRPO recipe notebook for the Cloud Sec Env.

Writes `colab/cloud_sec_env_grpo.ipynb` -- a runnable RL recipe that picks up
from the SFT'd Qwen2.5-7B adapter and applies GRPO using step-level rewards
from our env. Not executed during the hackathon due to compute budget; shipped
as a reproducible recipe for downstream experiments.

Run this script to (re)generate the notebook after editing the cell list.
"""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_TITLE = "Cloud Sec Env -- GRPO recipe (Qwen2.5-7B + TRL + step rewards)"

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        f"""# {NOTEBOOK_TITLE}

Reinforcement-learning recipe that picks up where the SFT notebook leaves off.
Continues fine-tuning Qwen2.5-7B-Instruct (with the LoRA adapter from
`cloud_sec_env_sft.ipynb`) using **GRPO** (Group Relative Policy Optimization)
on dense step-level rewards from our Cloud Sec Env.

> **NOTE.** This notebook is shipped as a *runnable recipe*. We did **not** run
> it during the OpenEnv hackathon (April 2026) due to a 6-hour wall-clock
> budget at the end -- meaningful GRPO requires several hours of A100 time.
> Everything below has been syntax-checked but not executed end-to-end.

**Why GRPO is a good fit for this env**
- Our reward scorer emits a *step-level* reward at every tool call (correct
  first tool, log->trace pivot, finds CHG-1891, reads state-lock Slack, ...
  plus penalties for unscoped logs / cloud-3 fixation). This gives GRPO a
  dense gradient instead of a single terminal pass/fail.
- The env is HTTP-deployable; we drive rollouts against the public Space.
- The deterministic keyword rubric gives reproducible terminal rewards with
  no API-key dependency during training.

**Pipeline**
1. Install deps
2. Load Qwen + SFT'd LoRA adapter
3. Build a state-action dataset from harvested SFT trajectories
4. Define a reward function that calls our env
5. Configure `GRPOTrainer`
6. (Notes) extending to full multi-turn rollouts
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
!pip install trl peft accelerate bitsandbytes datasets requests""",
    ),
    (
        "markdown",
        """## 2. Load Qwen2.5-7B + the SFT'd LoRA adapter

Adjust `SFT_ADAPTER_REPO` to point at your trained adapter. If you trained
it with `cloud_sec_env_sft.ipynb` and didn't push to the Hub, mount your
Drive or upload the `cloud_sec_sft_adapter` folder and load it from disk.""",
    ),
    (
        "code",
        '''from unsloth import FastLanguageModel

MAX_SEQ_LEN = 4096
BASE_MODEL = "unsloth/Qwen2.5-7B-Instruct"
SFT_ADAPTER_REPO = "Krishna3451112/cloud-sec-env-qwen-sft"  # TODO: replace if you forked

# Load base model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=MAX_SEQ_LEN,
    load_in_4bit=True,
)

# Apply the SFT'd LoRA. If you saved adapter to local /content, swap to that path.
model.load_adapter(SFT_ADAPTER_REPO, adapter_name="sft")
print("Loaded base + SFT adapter.")''',
    ),
    (
        "markdown",
        """## 3. Build a (prompt, state) dataset from SFT trajectories

GRPO samples N completions per prompt and computes advantages within the
group. We turn each saved SFT trajectory of N steps into N training prompts:
each prompt is the conversation state up to step k, and we let the model
generate step k itself; the reward function judges the result.""",
    ),
    (
        "code",
        '''from datasets import load_dataset, Dataset

DATASET_REPO = "Krishna3451112/cloud-sec-env-sft"
sft_data = load_dataset(DATASET_REPO, data_files="train.jsonl", split="train")

print(f"Loaded {len(sft_data)} SFT trajectories.")

# Each trajectory has a `messages` list: [system, user, assistant, user, assistant, ...].
# Every assistant turn is a JSON tool call. We turn each (state-up-to-step-k) prefix
# into a prompt the model should *generate the next assistant turn for*.

def trajectory_to_prompts(messages):
    """Yield (prompt_messages, ground_truth_action) pairs for each assistant turn."""
    for i, m in enumerate(messages):
        if m["role"] != "assistant":
            continue
        prefix = messages[:i]  # everything up to (but not including) this assistant turn
        yield prefix, m["content"]

prompts = []
for row in sft_data:
    for prefix, gt in trajectory_to_prompts(row["messages"]):
        # Render the prefix to a single training prompt string.
        prompt_text = tokenizer.apply_chat_template(
            prefix, tokenize=False, add_generation_prompt=True,
        )
        prompts.append({"prompt": prompt_text, "gt_completion": gt})

print(f"Built {len(prompts)} (state, target_action) pairs from {len(sft_data)} trajectories.")

# Drop the gt_completion -- GRPO doesn't need it; it samples + scores via reward.
grpo_dataset = Dataset.from_list(prompts).remove_columns(["gt_completion"])
print(f"GRPO dataset: {grpo_dataset}")''',
    ),
    (
        "markdown",
        """## 4. Reward function: parse completion, run env step, return step reward

For each model completion (a JSON tool call), we:
1. Parse the JSON.
2. Reset a fresh env locally (so each scoring run is independent).
3. Run the tool call -- this returns a step reward from our scorer.
4. Return that reward as a scalar.

This is a *single-step* reward signal. It teaches the model to choose
high-value first actions (correctly scoped `logs_search`, finds the right
ticket, etc.). It does **not** train multi-step planning -- see Section 6
for the multi-turn extension.""",
    ),
    (
        "code",
        '''import json, re

# We call the env via HTTP against a fresh /reset for every scoring pass --
# safe under concurrency on the Space (it allocates one CloudSecEnvironment
# per session) and avoids needing to install the env package in this notebook.
import requests

ENV_BASE = "https://Krishna3451112-cloud-sec-env-space.hf.space"


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
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
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


def score_completion(completion: str) -> float:
    """Score one model completion (a JSON tool call) by running it through a fresh env step.

    Returns the step reward (typically 0.0 to ~0.10). Format-invalid completions get -0.10
    so the model is mildly penalised for emitting non-JSON. Submit_answer at step 1
    gets terminal reward (likely 0 since no investigation happened).
    """
    parsed = extract_json(completion)
    if parsed is None or not isinstance(parsed.get("tool_name"), str):
        return -0.10

    # Fresh episode every score -- one HTTP /reset, one HTTP /step.
    try:
        requests.post(f"{ENV_BASE}/reset", json={}, timeout=30)
        action = {
            "tool_name": parsed["tool_name"],
            "arguments": parsed.get("arguments") or {},
            "reasoning": parsed.get("reasoning"),
        }
        r = requests.post(f"{ENV_BASE}/step", json={"action": action}, timeout=60).json()
        reward = float(r.get("reward") or 0.0)
        return reward
    except Exception:
        # Network blip -- treat as zero so we don't bias training.
        return 0.0


def grpo_reward_fn(prompts, completions, **kwargs):
    """TRL GRPOTrainer reward signature: receives lists of prompts + completions.

    Each completion is a list of token strings; we join them into a single string
    (TRL's behaviour varies by version -- this handles both).
    """
    rewards = []
    for c in completions:
        text = c if isinstance(c, str) else "".join(c)
        rewards.append(score_completion(text))
    return rewards''',
    ),
    (
        "markdown",
        """## 5. Configure and run `GRPOTrainer`

Hyperparameters sized for a single A100 (Colab Pro). Adjust `num_generations`
(group size) and `max_steps` to the budget you have. A reasonable single-GPU
run: 200 GRPO steps * 8 generations / step ~= 1600 total scored completions
(~1600 env HTTP calls -- fast against our Space).""",
    ),
    (
        "code",
        '''from trl import GRPOTrainer, GRPOConfig

config = GRPOConfig(
    output_dir="/content/cloud_sec_grpo_outputs",
    learning_rate=5e-6,                  # much lower than SFT; we are nudging, not relearning
    per_device_train_batch_size=1,
    gradient_accumulation_steps=4,
    num_generations=8,                   # group size for GRPO advantage
    max_completion_length=512,           # one JSON tool call fits comfortably
    max_prompt_length=3072,              # long enough for trajectory-prefix prompts
    max_steps=200,
    logging_steps=1,
    save_strategy="no",
    bf16=True,
    report_to="none",
    seed=3407,
)

trainer = GRPOTrainer(
    model=model,
    processing_class=tokenizer,
    reward_funcs=[grpo_reward_fn],
    args=config,
    train_dataset=grpo_dataset,
)

# trainer_stats = trainer.train()
# trainer.save_model("/content/cloud_sec_grpo_adapter")
print("Trainer constructed. Uncomment .train() above to run -- requires ~2-4 hours on A100.")''',
    ),
    (
        "markdown",
        """## 6. (Optional extension) Full multi-turn rollouts

The single-step reward in Section 4 trains good *individual* tool calls but
not multi-step planning -- it can't teach "use the trace_id from logs_search
in a follow-up trace_get". For that, you want full episode rollouts where
each completion is *the entire trajectory*.

The cleanest way to do that is to **replace the reward function** with one
that:
1. Treats the completion as a "policy" -- effectively re-runs the full
   episode against a fresh env, sampling each turn from the model.
2. Returns the terminal reward (or terminal + sum of step rewards).

This requires a custom rollout loop, since TRL's vanilla GRPOTrainer is
built around prompt->completion. Two practical options:

- **`verifiers`** (https://github.com/willccbb/verifiers): library purpose-built
  for multi-turn agentic GRPO. Wraps your env and handles the rollout.
- **Custom loop**: subclass `GRPOTrainer` and override the generation step to
  interleave model.generate() calls with env.step() calls.

If you go this route, the reward-shaping work in our env carries over
unchanged -- our scorer already emits both step-level *and* terminal rewards
that are well-suited to RL training.""",
    ),
    (
        "code",
        '''# Sketch of the multi-turn rollout loop -- not used in the simple GRPO recipe above.
# Provided for reference if you swap to a multi-turn trainer (e.g. `verifiers`).

def rollout_episode(messages_so_far, env_base=ENV_BASE, max_steps=30, temperature=0.7):
    """Run one full episode against the env, sampling each turn from the loaded model."""
    requests.post(f"{env_base}/reset", json={}, timeout=30)
    total = 0.0
    terminal = None
    submitted = False
    for step in range(max_steps):
        inputs = tokenizer.apply_chat_template(
            messages_so_far, return_tensors="pt", add_generation_prompt=True,
        ).to("cuda")
        outputs = model.generate(
            inputs, max_new_tokens=512, do_sample=True, temperature=temperature,
            pad_token_id=tokenizer.eos_token_id,
        )
        decoded = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
        parsed = extract_json(decoded)
        if parsed is None: break

        action = {
            "tool_name": parsed["tool_name"],
            "arguments": parsed.get("arguments") or {},
            "reasoning": parsed.get("reasoning"),
        }
        r = requests.post(f"{env_base}/step", json={"action": action}, timeout=60).json()
        total += float(r.get("reward") or 0.0)
        new_obs = r["observation"]
        messages_so_far.append({"role": "assistant", "content": decoded})
        messages_so_far.append({
            "role": "user",
            "content": f"[{new_obs[\\'observation_type\\'].upper()}]\\n{new_obs[\\'content\\']}",
        })
        if r.get("done"):
            if action["tool_name"] == "submit_answer":
                terminal = float(r.get("reward") or 0.0)
                submitted = True
            break
    return {"total": total, "terminal": terminal, "submitted": submitted}

# Use case for the multi-turn reward:
#   rollouts = [rollout_episode(initial_msgs.copy()) for _ in range(num_generations)]
#   rewards = [r["terminal"] if r["submitted"] else r["total"] for r in rollouts]
#
# Plug those rewards back into GRPO's advantage computation. See `verifiers` for a
# clean implementation.''',
    ),
    (
        "markdown",
        """## Done

**What this notebook ships**
- A working GRPO recipe wired to our deployed env (single-step rewards).
- A documented extension path to multi-turn rollouts.
- Explicit honesty about what was and wasn't run during the hackathon.

**Where to take it next**
- Run Section 5 on Colab Pro A100 for ~3 hours, save the adapter, re-run
  `colab/cloud_sec_env_eval.ipynb` to compare GRPO-tuned vs SFT-only.
- Add tasks 02-10 in `cloud_sec_env/data/` and re-train with task-mixed batches.
- Swap to `verifiers` for proper multi-turn agentic RL.""",
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
            "colab": {"name": "cloud_sec_env_grpo.ipynb", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
            "accelerator": "GPU",
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


def main() -> int:
    nb = build_notebook(CELLS)
    out = Path(__file__).resolve().parents[1] / "colab" / "cloud_sec_env_grpo.ipynb"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    main()
