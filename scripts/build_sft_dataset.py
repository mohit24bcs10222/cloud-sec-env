"""Build an SFT training dataset from harvested Opus trajectories.

Reads trajectory JSON files (produced by `cloud_sec_env.agent.run`), filters by
terminal_reward, and emits a JSONL file ready for SFT.

Each output line is one trajectory rendered as a `{"messages": [...]}` object
matching Qwen's chat template, with assistant turns formatted as the JSON the
QwenAdapter expects (so the fine-tuned model produces parseable JSON
responses end-to-end).

Usage:
    python scripts/build_sft_dataset.py --min-reward 0.85 \\
        --in trajectories/ --out data/sft/cloud_sec_train.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sibling package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud_sec_env.agent.adapters.qwen_adapter import QWEN_SYSTEM_PROMPT


def trajectory_to_messages(traj: dict) -> dict | None:
    """Convert one trajectory JSON into a {messages: [...]} SFT example.

    Returns None if the trajectory isn't usable (e.g. no submit_answer).
    """
    steps = traj.get("steps", [])
    if not steps:
        return None
    if not traj.get("terminated_cleanly"):
        return None  # only train on rollouts that reached submit_answer

    messages: list[dict] = [{"role": "system", "content": QWEN_SYSTEM_PROMPT}]

    # First user turn = initial alert. We don't have the alert text in the
    # trajectory file, so we read it from the env's data folder.
    task_id = traj.get("task_id", "task_01_oidc_rotation")
    alert_path = Path(__file__).resolve().parents[1] / "cloud_sec_env" / "data" / task_id / "alert.json"
    alert = json.loads(alert_path.read_text(encoding="utf-8"))
    initial_user = alert.get("rendered_text", "") or json.dumps(alert)
    messages.append({"role": "user", "content": initial_user})

    for step in steps:
        action = step["action"]
        # Assistant turn: JSON object Qwen should produce
        assistant_payload = {
            "reasoning": action.get("reasoning") or "",
            "tool_name": action["tool_name"],
            "arguments": action.get("arguments") or {},
        }
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(assistant_payload, ensure_ascii=False),
            }
        )
        # User turn: tagged tool result, matching what QwenAdapter.observe writes.
        obs_type = (step.get("observation_type") or "tool_result").upper()
        user_content = f"[{obs_type}]\n" + (step.get("content") or "")
        messages.append({"role": "user", "content": user_content})

    # The last step's user message (post-submit evaluation) isn't actually
    # used by the model -- the submit_answer is the terminal action. Trim
    # the trailing user turn so the data ends on an assistant submit_answer.
    if messages and messages[-1]["role"] == "user":
        messages.pop()

    return {
        "messages": messages,
        "task_id": task_id,
        "model_source": traj.get("model"),
        "terminal_reward": traj.get("terminal_reward"),
        "total_reward": traj.get("total_reward"),
        "num_steps": traj.get("num_steps"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", default="trajectories", help="Trajectory dir or single JSON file")
    parser.add_argument("--out", default="data/sft/cloud_sec_train.jsonl", help="Output JSONL path")
    parser.add_argument("--min-reward", type=float, default=0.85, help="Keep trajectories with terminal_reward >= this")
    parser.add_argument(
        "--model-prefix",
        default=None,
        help="Optional: only include trajectories whose `model` starts with this string (e.g. 'claude-')",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap on number of trajectories")
    args = parser.parse_args()

    inp = Path(args.inp)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if inp.is_dir():
        files = sorted(p for p in inp.glob("*.json") if "summary" not in p.name)
    else:
        files = [inp]

    kept = 0
    skipped_low = 0
    skipped_unfinished = 0
    skipped_other = 0
    written: list[dict] = []
    rejected_reasons: dict[str, int] = {}

    for f in files:
        try:
            traj = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            skipped_other += 1
            rejected_reasons[f"parse_error: {type(e).__name__}"] = rejected_reasons.get(f"parse_error: {type(e).__name__}", 0) + 1
            continue

        if args.model_prefix and not (traj.get("model") or "").startswith(args.model_prefix):
            skipped_other += 1
            continue

        terminal = traj.get("terminal_reward")
        if terminal is None:
            skipped_unfinished += 1
            continue
        if terminal < args.min_reward:
            skipped_low += 1
            continue

        record = trajectory_to_messages(traj)
        if record is None:
            skipped_unfinished += 1
            continue

        written.append(record)
        if args.limit and len(written) >= args.limit:
            break

    with out.open("w", encoding="utf-8") as fh:
        for record in written:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    kept = len(written)

    print(f"Trajectories scanned:           {len(files)}")
    print(f"Kept (terminal >= {args.min_reward:.2f}):     {kept}")
    print(f"Skipped (low terminal):         {skipped_low}")
    print(f"Skipped (unfinished/None):      {skipped_unfinished}")
    print(f"Skipped (other):                {skipped_other}")
    print(f"Output: {out}")

    # Quick sanity stats on output
    if written:
        avg_steps = sum(r.get("num_steps", 0) for r in written) / len(written)
        avg_reward = sum(r.get("terminal_reward", 0.0) for r in written) / len(written)
        avg_messages = sum(len(r["messages"]) for r in written) / len(written)
        print(f"Avg steps per kept trajectory:  {avg_steps:.1f}")
        print(f"Avg terminal reward:            {avg_reward:.3f}")
        print(f"Avg messages per example:       {avg_messages:.1f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
