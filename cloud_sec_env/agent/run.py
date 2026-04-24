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

from typing import Optional

from dotenv import load_dotenv

from .adapters.anthropic_adapter import AnthropicAdapter
from .adapters.qwen_adapter import QwenAdapter
from .harness import RolloutHarness


# Load .env from project root (two levels up from this file) before anything else.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


def _build_adapter(model: str, temperature: float, verbose: bool):
    """Pick the right adapter based on the model name prefix."""
    if model.startswith("claude-") or model.startswith("anthropic/"):
        return AnthropicAdapter(model=model, temperature=temperature, verbose=verbose)
    if model.startswith("Qwen/") or "qwen" in model.lower():
        return QwenAdapter(model=model, temperature=temperature, verbose=verbose)
    raise ValueError(
        f"Unknown model '{model}'. Expected prefix 'claude-' / 'Qwen/' (or a name containing 'qwen')."
    )


def _check_credentials(model: str) -> Optional[str]:
    """Return an error string if required credentials aren't in env; None if OK."""
    if model.startswith("claude-") or model.startswith("anthropic/"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return (
                "ANTHROPIC_API_KEY not set.\n"
                "  1. Edit .env at the project root and fill ANTHROPIC_API_KEY=sk-ant-...\n"
                "  2. Or export it in your shell: export ANTHROPIC_API_KEY=sk-ant-..."
            )
    elif model.startswith("Qwen/") or "qwen" in model.lower():
        if not os.environ.get("HF_TOKEN"):
            return (
                "HF_TOKEN not set.\n"
                "  1. Create a token at https://huggingface.co/settings/tokens\n"
                "  2. Edit .env at the project root and fill HF_TOKEN=hf_...\n"
                "  3. Or export it in your shell: export HF_TOKEN=hf_..."
            )
    return None


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

    cred_err = _check_credentials(args.model)
    if cred_err:
        print(f"ERROR: {cred_err}", file=sys.stderr)
        return 1

    out_root = Path(args.out) if args.out else Path("trajectories")
    out_root.mkdir(parents=True, exist_ok=True)

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results: list[dict] = []
    for i in range(args.n):
        adapter = _build_adapter(args.model, args.temperature, args.verbose)
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

        # Save per-rollout JSON. Sanitize model name for filesystem safety.
        safe_model = args.model.replace("/", "__").replace("\\", "__")
        filename = f"{args.task}_{safe_model}_{run_stamp}_r{i+1}.json"
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
        safe_model = args.model.replace("/", "__").replace("\\", "__")
        summary_path = out_root / f"{args.task}_{safe_model}_{run_stamp}_summary.json"
        summary_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"[run] batch summary -> {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
