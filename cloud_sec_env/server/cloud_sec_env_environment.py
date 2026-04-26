# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
PagerBench Environment.

Wires the tool layer + reward scorer into OpenEnv's reset/step interface.
Step-level rewards feed dense training signal; terminal reward evaluates
the final submit_answer against ground_truth.yaml.
"""

from __future__ import annotations

import os
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import CloudSecAction, CloudSecObservation
    from .data_loader import DataStore
    from .llm_judge import LLMJudge
    from .reward import RewardScorer
    from .tools import TOOL_REGISTRY, ToolError, call_tool
except (ImportError, ValueError):
    # Fallback for top-level-package execution (HF Spaces uvicorn entrypoint).
    from models import CloudSecAction, CloudSecObservation
    from server.data_loader import DataStore
    from server.llm_judge import LLMJudge
    from server.reward import RewardScorer
    from server.tools import TOOL_REGISTRY, ToolError, call_tool


MAX_STEPS = 30


def _build_judge() -> "LLMJudge | None":
    """Construct an LLM judge if ANTHROPIC_API_KEY is set AND judge isn't disabled.

    Env vars:
      - ANTHROPIC_API_KEY: required for judge.
      - CLOUD_SEC_DISABLE_JUDGE=1: force-fallback to keyword rubric
        (useful for fast training loops without API cost).
    """
    if os.environ.get("CLOUD_SEC_DISABLE_JUDGE") == "1":
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        return LLMJudge()
    except Exception:
        return None


class CloudSecEnvironment(Environment):
    """Cloud Sec incident-investigation environment."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self, task_id: str = "task_01_oidc_rotation"):
        self._store = DataStore(task_id=task_id)
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._scorer = RewardScorer(self._store.ground_truth, judge=_build_judge())
        # Trajectory log for reward scoring / analysis. Cleared on reset.
        self._trajectory: list[dict] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> CloudSecObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._scorer.reset()
        self._trajectory = []

        alert_text = self._store.alert.get("rendered_text") or ""
        return CloudSecObservation(
            content=alert_text,
            data={"alert": self._store.alert},
            observation_type="alert",
            steps_remaining=MAX_STEPS,
            done=False,
            reward=0.0,
            metadata={"episode_id": self._state.episode_id, "task_id": self._store.task_id},
        )

    def step(self, action: CloudSecAction) -> CloudSecObservation:  # type: ignore[override]
        self._state.step_count += 1
        steps_remaining = max(0, MAX_STEPS - self._state.step_count)

        # -------- Step budget check --------
        if steps_remaining == 0 and action.tool_name != "submit_answer":
            return self._out_of_steps()

        # -------- Terminal: submit_answer --------
        if action.tool_name == "submit_answer":
            return self._handle_submit(action, steps_remaining)

        # -------- Regular tool call --------
        try:
            content, data = call_tool(action.tool_name, action.arguments or {}, self._store)
            observation_type = "tool_result"
        except ToolError as e:
            content = f"ERROR calling {action.tool_name}: {e}"
            data = {"error": str(e), "tool_name": action.tool_name, "arguments": action.arguments or {}}
            observation_type = "error"
        except Exception as e:
            # Defensive: any other tool exception (e.g. TypeError from a list passed
            # where a string was expected) becomes an error observation rather than
            # crashing the episode. Agent gets a chance to retry with valid args.
            content = f"ERROR calling {action.tool_name}: {type(e).__name__}: {e}"
            data = {"error": f"{type(e).__name__}: {e}", "tool_name": action.tool_name, "arguments": action.arguments or {}}
            observation_type = "error"

        step_reward, step_hits = self._scorer.score_step(
            tool_name=action.tool_name,
            arguments=action.arguments or {},
            observation_type=observation_type,
            tool_data=data if observation_type == "tool_result" else None,
        )

        self._log_trajectory(
            action=action,
            observation_type=observation_type,
            content=content,
            tool_data=data,
            step_reward=step_reward,
            step_hits=step_hits,
        )

        return CloudSecObservation(
            content=content,
            data=data,
            observation_type=observation_type,
            steps_remaining=steps_remaining,
            done=False,
            reward=step_reward,
            metadata={"step_reward_hits": step_hits},
        )

    @property
    def state(self) -> State:
        return self._state

    # ------------------------------------------------------------------
    # Terminal path
    # ------------------------------------------------------------------

    def _handle_submit(self, action: CloudSecAction, steps_remaining: int) -> CloudSecObservation:
        args = action.arguments or {}
        root_cause = args.get("root_cause", "")
        fix = args.get("fix", "")

        # Pass the trajectory so far (not including this submit step) to the
        # scorer -- the LLM judge uses it to verify claims against evidence.
        terminal_reward, reward_breakdown = self._scorer.score_terminal(
            root_cause, fix, trajectory=list(self._trajectory)
        )
        scorer_summary = self._scorer.summary()

        summary_lines = ["Evaluation (deterministic keyword rubric):"]
        for component, info in reward_breakdown.items():
            if component.startswith("_"):
                # Auxiliary entries (_judge, _judge_error). Just summarise.
                if component == "_judge":
                    judge_total = info.get("score")
                    err = info.get("judge_error")
                    if err:
                        summary_lines.append(f"  [JUDGE] auxiliary LLM-judge errored: {err}")
                    elif judge_total is not None:
                        summary_lines.append(
                            f"  [JUDGE] auxiliary LLM-judge ran -- score={judge_total:.3f} "
                            f"(see metadata.judge for per-dimension breakdown + justifications)"
                        )
                continue
            weight = info.get("weight", 0.0)
            hit_marker = "YES" if info.get("hit") else "NO "
            summary_lines.append(f"  [{hit_marker}] {component}  (weight={weight})")
        summary_lines.append("")
        summary_lines.append(f"Terminal reward: {terminal_reward:.3f} / 1.000")
        summary_lines.append(f"Step reward accumulated during episode: {scorer_summary['total_step_reward']:.3f}")
        summary_lines.append(f"Achievements earned: {scorer_summary['achievements_earned']}")

        self._log_trajectory(
            action=action,
            observation_type="evaluation",
            content="\n".join(summary_lines),
            tool_data={
                "reward_breakdown": reward_breakdown,
                "terminal_reward": terminal_reward,
                "scorer_summary": scorer_summary,
            },
            step_reward=terminal_reward,
            step_hits=list(reward_breakdown.keys()),
        )

        return CloudSecObservation(
            content="\n".join(summary_lines),
            data={
                "submitted": {"root_cause": root_cause, "fix": fix},
                "terminal_reward": terminal_reward,
                "reward_breakdown": reward_breakdown,
                "scorer_summary": scorer_summary,
            },
            observation_type="evaluation",
            steps_remaining=steps_remaining,
            done=True,
            reward=terminal_reward,
            metadata={},
        )

    def _out_of_steps(self) -> CloudSecObservation:
        self._log_trajectory(
            action=None,
            observation_type="error",
            content="out_of_steps",
            tool_data=None,
            step_reward=0.0,
            step_hits=[],
        )
        return CloudSecObservation(
            content="Step budget exhausted (30 steps). Episode terminated without an answer. Terminal reward = 0.",
            data={"reason": "out_of_steps", "scorer_summary": self._scorer.summary()},
            observation_type="error",
            steps_remaining=0,
            done=True,
            reward=0.0,
            metadata={"reason": "out_of_steps"},
        )

    # ------------------------------------------------------------------
    # Trajectory logging
    # ------------------------------------------------------------------

    def _log_trajectory(
        self,
        action: CloudSecAction | None,
        observation_type: str,
        content: str,
        tool_data: dict | None,
        step_reward: float,
        step_hits: list[str],
    ) -> None:
        entry = {
            "step": self._state.step_count,
            "action": None if action is None else {
                "tool_name": action.tool_name,
                "arguments": action.arguments or {},
                "reasoning": action.reasoning,
            },
            "observation_type": observation_type,
            "content_preview": content[:400] if content else "",
            "step_reward": step_reward,
            "step_hits": step_hits,
            "tool_data_keys": list((tool_data or {}).keys()) if tool_data else [],
        }
        self._trajectory.append(entry)

    @property
    def trajectory(self) -> list[dict]:
        """Read-only view of the current episode's trajectory log."""
        return list(self._trajectory)
