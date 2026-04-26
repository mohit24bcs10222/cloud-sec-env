"""End-to-end evaluation against the deployed HF Space env.

Drives a model (Anthropic native tool-use OR HF Inference prompted-JSON) through
N full episodes against the live env on HuggingFace Spaces, aggregates rewards,
and prints a markdown summary table.

This is the closest thing we have to "judge-friendly reproducibility": one
command, hits the public Space URL, prints headline numbers.

Usage:
    # Default: 5 episodes of Opus against the live Space
    python scripts/eval_against_space.py

    # Qwen + SFT adapter via local model (requires huggingface-cli login)
    python scripts/eval_against_space.py --model Qwen/Qwen2.5-7B-Instruct --n 10

    # Custom Space URL (e.g. you've forked the repo)
    python scripts/eval_against_space.py --space-url https://your-space.hf.space
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

import requests
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_SPACE_URL = "https://Krishna3451112-cloud-sec-env-space.hf.space"


# ---------------------------------------------------------------------------
# Remote env client (thin HTTP wrapper)
# ---------------------------------------------------------------------------

class RemoteEnv:
    """Minimal HTTP client for an OpenEnv-compatible Space."""

    def __init__(self, base_url: str, timeout_s: float = 120.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout_s

    def reset(self) -> dict[str, Any]:
        r = requests.post(f"{self.base}/reset", json={}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["observation"]

    def step(self, action: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(
            f"{self.base}/step",
            json={"action": action},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Episode driver -- mirrors the local harness but talks to a remote env
# ---------------------------------------------------------------------------

def run_episode_remote(
    adapter,
    env: RemoteEnv,
    max_steps: int = 30,
    verbose: bool = False,
) -> dict[str, Any]:
    obs = env.reset()
    adapter.reset(obs["content"])

    total_reward = 0.0
    terminal_reward: float | None = None
    submitted = False
    stop_reason = "budget_exhausted"
    num_steps = 0

    for step_i in range(1, max_steps + 1):
        try:
            action = adapter.get_action()
        except Exception as e:
            stop_reason = f"adapter_error:{type(e).__name__}:{e}"
            break
        if action is None:
            stop_reason = "adapter_returned_none"
            break
        if verbose:
            print(f"  step {step_i}: {action.tool_name}({list((action.arguments or {}).keys())})")
        try:
            payload = env.step({
                "tool_name": action.tool_name,
                "arguments": action.arguments or {},
                "reasoning": action.reasoning,
            })
        except Exception as e:
            stop_reason = f"env_error:{type(e).__name__}:{e}"
            break

        new_obs = payload["observation"]
        reward = payload.get("reward") or 0.0
        total_reward += reward
        num_steps = step_i

        adapter.observe(new_obs["content"], new_obs["observation_type"])

        if payload.get("done"):
            if action.tool_name == "submit_answer":
                terminal_reward = reward
                submitted = True
                stop_reason = "submit"
            else:
                stop_reason = f"done:{new_obs.get('observation_type')}"
            break

    return {
        "submitted": submitted,
        "terminal_reward": terminal_reward,
        "total_reward": round(total_reward, 4),
        "num_steps": num_steps,
        "stop_reason": stop_reason,
    }


# ---------------------------------------------------------------------------
# Adapter selection
# ---------------------------------------------------------------------------

def _build_adapter(model: str, temperature: float, verbose: bool):
    if model.startswith("claude-") or model.startswith("anthropic/"):
        from cloud_sec_env.agent.adapters.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter(model=model, temperature=temperature, verbose=verbose)
    if model.startswith("Qwen/") or "qwen" in model.lower():
        from cloud_sec_env.agent.adapters.qwen_adapter import QwenAdapter
        return QwenAdapter(model=model, temperature=temperature, verbose=verbose)
    raise ValueError(
        f"Unknown model '{model}'. Expected prefix 'claude-' or 'Qwen/'."
    )


def _check_credentials(model: str) -> str | None:
    if model.startswith("claude-") or model.startswith("anthropic/"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return "ANTHROPIC_API_KEY not set in .env or shell."
    elif model.startswith("Qwen/") or "qwen" in model.lower():
        if not os.environ.get("HF_TOKEN"):
            return "HF_TOKEN not set in .env or shell."
    return None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def render_markdown(model: str, space_url: str, results: list[dict[str, Any]]) -> str:
    n = len(results)
    submitted = [r for r in results if r["submitted"]]
    submit_rate = 100.0 * len(submitted) / n if n else 0.0
    mean_terminal = mean([r["terminal_reward"] for r in submitted]) if submitted else 0.0
    mean_total = mean([r["total_reward"] for r in results]) if results else 0.0
    mean_steps = mean([r["num_steps"] for r in results]) if results else 0.0

    lines = [
        f"## Eval results: {model}",
        "",
        f"- Space: `{space_url}`",
        f"- Episodes: {n}",
        f"- Submission rate: **{submit_rate:.0f}%** ({len(submitted)}/{n})",
        f"- Mean terminal reward (submitted only): **{mean_terminal:.3f}**",
        f"- Mean total reward (incl. step rewards, all episodes): {mean_total:.3f}",
        f"- Mean steps per episode: {mean_steps:.1f}",
        "",
        "| # | submitted | terminal | total | steps | stop |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        term = f"{r['terminal_reward']:.3f}" if r["terminal_reward"] is not None else "-"
        lines.append(
            f"| {i} | {'YES' if r['submitted'] else 'NO'} | {term} | "
            f"{r['total_reward']:.3f} | {r['num_steps']} | `{r['stop_reason']}` |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Run N episodes against the deployed env Space.")
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--max-steps", type=int, default=30)
    p.add_argument("--space-url", default=DEFAULT_SPACE_URL)
    p.add_argument("--out", default=None, help="Optional path to save markdown summary.")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    err = _check_credentials(args.model)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    env = RemoteEnv(args.space_url)
    # Sanity ping
    try:
        ping = env.reset()
        print(f"[eval] Space reachable. Initial observation_type={ping['observation_type']}, "
              f"steps_remaining={ping['steps_remaining']}")
    except Exception as e:
        print(f"ERROR: Space unreachable at {args.space_url}: {e}", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    for i in range(args.n):
        print(f"[eval] episode {i+1}/{args.n} ...")
        adapter = _build_adapter(args.model, args.temperature, args.verbose)
        t0 = time.monotonic()
        res = run_episode_remote(adapter, env, max_steps=args.max_steps, verbose=args.verbose)
        res["duration_s"] = round(time.monotonic() - t0, 1)
        results.append(res)
        term = f"{res['terminal_reward']:.3f}" if res['terminal_reward'] is not None else "-"
        print(f"[eval]   submit={res['submitted']} terminal={term} "
              f"total={res['total_reward']:.3f} steps={res['num_steps']} "
              f"stop={res['stop_reason']} ({res['duration_s']}s)")

    summary_md = render_markdown(args.model, args.space_url, results)
    print()
    print(summary_md)

    if args.out:
        Path(args.out).write_text(summary_md, encoding="utf-8")
        print(f"\n[eval] saved -> {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
