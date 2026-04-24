# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
CLI runner for a single episode rollout.

Examples:
    # One Opus rollout at default temperature 0.7
    python -m cloud_sec_env.agent.run --model claude-opus-4-7

    # Verbose, custom output path
    python -m cloud_sec_env.agent.run --model claude-opus-4-7 --verbose --out trajectories/run1.json

    # Run many rollouts for trajectory harvesting (Task #13)
    python -m cloud_sec_env.agent.run --model claude-opus-4-7 --n 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .adapters.anthropic_adapter import AnthropicAdapter
from .harness import RolloutHarness


# Load .env from project root (two levels up from this file) before anything else.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an Opus rollout against the Cloud Sec env.")
    parser.add_argument("--model", default="claude-opus-4-7", help="Anthropic model name.")
    parser.add_argument("--task", default="task_01_oidc_rotation", help="Task ID.")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--n", type=int, default=1, help="Number of rollouts to run sequentially.")
    parser.add_argument("--out", default=None, help="Output path (single rollout) or dir (multiple).")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY not set.\n"
            "  1. Edit .env at the project root and put your key after ANTHROPIC_API_KEY=\n"
            "  2. Or export it in your shell: export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        return 1

    out_root = Path(args.out) if args.out else Path("trajectories")
    out_root.mkdir(parents=True, exist_ok=True)

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results: list[dict] = []
    for i in range(args.n):
        adapter = AnthropicAdapter(
            model=args.model,
            temperature=args.temperature,
            verbose=args.verbose,
        )
        harness = RolloutHarness(
            adapter=adapter,
            task_id=args.task,
            max_steps=args.max_steps,
            verbose=args.verbose,
        )

        print(f"[run] starting rollout {i+1}/{args.n} (model={args.model}, temp={args.temperature})")
        try:
            trajectory = harness.run_episode()
        except Exception as e:
            print(f"[run] rollout failed: {type(e).__name__}: {e}", file=sys.stderr)
            continue

        # Save per-rollout JSON.
        filename = f"{args.task}_{args.model}_{run_stamp}_r{i+1}.json"
        out_path = out_root / filename
        out_path.write_text(json.dumps(trajectory, indent=2, default=str), encoding="utf-8")
        print(
            f"[run]   stop_reason={trajectory['stop_reason']}  "
            f"steps={trajectory['num_steps']}  "
            f"total_reward={trajectory['total_reward']:.3f}  "
            f"terminal={trajectory['terminal_reward']}"
        )
        print(f"[run]   saved -> {out_path}")
        results.append({"path": str(out_path), "summary": {k: v for k, v in trajectory.items() if k != "steps"}})

    # Write a batch summary if more than one rollout.
    if args.n > 1:
        summary_path = out_root / f"{args.task}_{args.model}_{run_stamp}_summary.json"
        summary_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"[run] batch summary -> {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
