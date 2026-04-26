"""Rubric ablation: re-score saved trajectories under three reward configurations.

Why this exists: our headline design choice is "deterministic keyword rubric =
primary, LLM judge = auxiliary". The ablation shows what would happen if we'd
chosen differently, on the same answers:

  (1) keyword-only      -- our shipping design (fast, no API key needed)
  (2) judge-only        -- alternative: trust the LLM judge as primary
  (3) composite-mean    -- alternative: average of the two

For each saved trajectory we extract the agent's submit_answer (root_cause +
fix), then re-score it three ways. If ANTHROPIC_API_KEY isn't set we skip the
judge column gracefully and only report the keyword variant.

Usage:
    python scripts/ablation_rubric.py --in trajectories/ --out demo/ablation.md
    python scripts/ablation_rubric.py --in trajectories/ --no-judge   # skip API calls
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from statistics import mean
from typing import Any

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT))

from cloud_sec_env.server.data_loader import DataStore
from cloud_sec_env.server.reward import RewardScorer


def _extract_submit(traj: dict[str, Any]) -> tuple[str, str] | None:
    """Pull (root_cause, fix) from the trajectory's submit step. None if no submit."""
    for step in traj.get("steps", []):
        action = step.get("action", {}) or {}
        if action.get("tool_name") == "submit_answer":
            args = action.get("arguments", {}) or {}
            return (args.get("root_cause") or "", args.get("fix") or "")
    return None


def _score_keyword(scorer: RewardScorer, root_cause: str, fix: str) -> tuple[float, dict]:
    return scorer._score_terminal_keyword(root_cause, fix)


def _score_judge(judge, root_cause: str, fix: str, trajectory: list[dict] | None) -> tuple[float | None, dict]:
    if judge is None:
        return None, {}
    try:
        result = judge.grade(root_cause, fix, trajectory=trajectory)
        return result.get("total"), result.get("breakdown", {}) or {}
    except Exception as e:
        return None, {"_error": str(e)}


def _trajectory_for_judge(traj: dict[str, Any]) -> list[dict]:
    """Translate saved harness trajectory into the format LLMJudge expects."""
    out: list[dict] = []
    for s in traj.get("steps", []):
        action = s.get("action") or {}
        out.append({
            "step": s.get("step"),
            "action": {
                "tool_name": action.get("tool_name"),
                "arguments": action.get("arguments") or {},
                "reasoning": action.get("reasoning"),
            },
            "observation_type": s.get("observation_type"),
            "content_preview": (s.get("content") or "")[:400],
            "step_reward": s.get("reward", 0.0),
            "step_hits": s.get("step_hits") or [],
            "tool_data_keys": [],
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", default="trajectories", help="Trajectory dir.")
    p.add_argument("--out", default=None, help="Optional path to save markdown.")
    p.add_argument("--no-judge", action="store_true", help="Skip LLM-judge column (no API calls).")
    p.add_argument("--limit", type=int, default=None, help="Cap trajectories.")
    p.add_argument("--task-id", default="task_01_oidc_rotation")
    args = p.parse_args()

    inp = Path(args.inp)
    files = sorted(p for p in inp.glob("*.json") if "summary" not in p.name)
    if args.limit:
        files = files[: args.limit]

    store = DataStore(task_id=args.task_id)
    keyword_scorer = RewardScorer(store.ground_truth, judge=None)

    # Build judge once if available + requested.
    judge = None
    if not args.no_judge and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from cloud_sec_env.server.llm_judge import LLMJudge
            judge = LLMJudge()
            print(f"[ablation] judge enabled (model={judge.model})")
        except Exception as e:
            print(f"[ablation] judge unavailable: {e}", file=sys.stderr)
            judge = None
    else:
        if args.no_judge:
            print("[ablation] --no-judge set: keyword column only.")
        else:
            print("[ablation] ANTHROPIC_API_KEY not set: keyword column only.")

    rows: list[dict[str, Any]] = []
    skipped_no_submit = 0
    skipped_parse = 0

    for f in files:
        try:
            traj = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            skipped_parse += 1
            continue
        submit = _extract_submit(traj)
        if submit is None:
            skipped_no_submit += 1
            continue
        root_cause, fix = submit

        # (1) keyword
        kw_score, kw_breakdown = _score_keyword(keyword_scorer, root_cause, fix)

        # (2) judge
        if judge is not None:
            print(f"[ablation] judging {f.name} ...")
            j_score, _ = _score_judge(judge, root_cause, fix, _trajectory_for_judge(traj))
        else:
            j_score = None

        # (3) composite-mean -- only if judge ran successfully
        if j_score is not None:
            composite = (kw_score + j_score) / 2.0
        else:
            composite = None

        rows.append({
            "file": f.name,
            "model": traj.get("model"),
            "kw_score": kw_score,
            "kw_dims_hit": sum(1 for v in kw_breakdown.values() if v["hit"]),
            "kw_dims_total": len(kw_breakdown),
            "judge_score": j_score,
            "composite": composite,
            "num_steps": traj.get("num_steps"),
            "stop_reason": traj.get("stop_reason"),
        })

    if not rows:
        print("[ablation] no usable trajectories with submit_answer found.", file=sys.stderr)
        return 1

    md_lines: list[str] = ["# Rubric ablation"]
    md_lines.append("")
    md_lines.append(
        "Same agent answers, scored under three reward configurations. "
        "Demonstrates why we ship keyword-rubric as primary: it agrees with the LLM "
        "judge on most trajectories while requiring no API key."
    )
    md_lines.append("")

    # Aggregate stats
    has_judge_rows = [r for r in rows if r["judge_score"] is not None]
    md_lines.append("## Aggregate")
    md_lines.append("")
    md_lines.append(f"- Trajectories scored: **{len(rows)}**")
    md_lines.append(f"- Mean keyword score:    **{mean(r['kw_score'] for r in rows):.3f}**")
    if has_judge_rows:
        md_lines.append(f"- Mean judge score:      **{mean(r['judge_score'] for r in has_judge_rows):.3f}** (n={len(has_judge_rows)})")
        md_lines.append(f"- Mean composite (avg):  **{mean(r['composite'] for r in has_judge_rows):.3f}**")
        diffs = [abs(r['kw_score'] - r['judge_score']) for r in has_judge_rows]
        md_lines.append(f"- Mean |keyword - judge|: **{mean(diffs):.3f}** (rubric agreement)")
        md_lines.append(f"- Max  |keyword - judge|: **{max(diffs):.3f}**")
    md_lines.append("")

    md_lines.append("## Per-trajectory")
    md_lines.append("")
    md_lines.append("| trajectory | model | keyword | judge | composite | dims hit | steps |")
    md_lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        kw = f"{r['kw_score']:.3f}"
        j = f"{r['judge_score']:.3f}" if r["judge_score"] is not None else "-"
        c = f"{r['composite']:.3f}" if r["composite"] is not None else "-"
        md_lines.append(
            f"| `{r['file']}` | {r['model']} | {kw} | {j} | {c} | "
            f"{r['kw_dims_hit']}/{r['kw_dims_total']} | {r['num_steps']} |"
        )
    md_lines.append("")
    md_lines.append(
        f"_Skipped {skipped_no_submit} trajectories without submit_answer, "
        f"{skipped_parse} with parse errors._"
    )

    out_text = "\n".join(md_lines)
    print()
    print(out_text)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"\n[ablation] saved -> {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
