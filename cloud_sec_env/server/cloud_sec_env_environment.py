# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Cloud Sec Env Environment.

Wires the tool layer into OpenEnv's reset/step interface.

Reward handling is split:
  - Step-level rewards: placeholder here (0.0). Person B's reward scorer
    (Task #10) replaces this by implementing `score_step()`.
  - Terminal reward on submit_answer: placeholder here (0.0). Same hook.
"""

from __future__ import annotations

from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import CloudSecAction, CloudSecObservation
    from .data_loader import DataStore
    from .tools import TOOL_REGISTRY, ToolError, call_tool
except ImportError:
    from models import CloudSecAction, CloudSecObservation
    from server.data_loader import DataStore
    from server.tools import TOOL_REGISTRY, ToolError, call_tool


MAX_STEPS = 30


def _advocates_rollback(fix_lc: str) -> bool:
    """Crude heuristic: detects whether the fix recommends a global rollback.
    True means 'rollback' appears without a nearby negation (do not / don't / avoid).
    Person B's reward scorer replaces this with something better."""
    for term in ("rollback", "roll back", "revert the rotation", "revert rotation"):
        idx = 0
        while True:
            pos = fix_lc.find(term, idx)
            if pos == -1:
                break
            before = fix_lc[max(0, pos - 40):pos]
            negations = ("do not", "don't", "avoid", "not to", "must not", "never")
            if not any(n in before for n in negations):
                return True
            idx = pos + len(term)
    return False


class CloudSecEnvironment(Environment):
    """Cloud Sec incident-investigation environment."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self, task_id: str = "task_01_oidc_rotation"):
        self._store = DataStore(task_id=task_id)
        self._state = State(episode_id=str(uuid4()), step_count=0)
        # Trajectory log for reward scoring / analysis. Cleared on reset.
        self._trajectory: list[dict] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> CloudSecObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
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
        except ToolError as e:
            self._log_trajectory(action, "error", str(e))
            return CloudSecObservation(
                content=f"ERROR calling {action.tool_name}: {e}",
                data={"error": str(e), "tool_name": action.tool_name, "arguments": action.arguments or {}},
                observation_type="error",
                steps_remaining=steps_remaining,
                done=False,
                reward=self._score_step(action, observation_type="error", tool_data=None),
                metadata={},
            )

        self._log_trajectory(action, "tool_result", content, tool_data=data)
        return CloudSecObservation(
            content=content,
            data=data,
            observation_type="tool_result",
            steps_remaining=steps_remaining,
            done=False,
            reward=self._score_step(action, observation_type="tool_result", tool_data=data),
            metadata={},
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

        terminal_reward, reward_breakdown = self._score_terminal(root_cause, fix)

        summary_lines = ["Evaluation:"]
        for component, info in reward_breakdown.items():
            hit_marker = "YES" if info["hit"] else "NO "
            summary_lines.append(f"  [{hit_marker}] {component}  (weight={info['weight']})")
        summary_lines.append(f"Terminal reward: {terminal_reward:.3f} / 1.000")

        self._log_trajectory(action, "evaluation", "\n".join(summary_lines), tool_data={"reward_breakdown": reward_breakdown, "terminal_reward": terminal_reward})

        return CloudSecObservation(
            content="\n".join(summary_lines),
            data={
                "submitted": {"root_cause": root_cause, "fix": fix},
                "terminal_reward": terminal_reward,
                "reward_breakdown": reward_breakdown,
            },
            observation_type="evaluation",
            steps_remaining=steps_remaining,
            done=True,
            reward=terminal_reward,
            metadata={},
        )

    def _out_of_steps(self) -> CloudSecObservation:
        self._log_trajectory(None, "error", "out_of_steps")
        return CloudSecObservation(
            content="Step budget exhausted (30 steps). Episode terminated without an answer. Terminal reward = 0.",
            data={"reason": "out_of_steps"},
            observation_type="error",
            steps_remaining=0,
            done=True,
            reward=0.0,
            metadata={"reason": "out_of_steps"},
        )

    # ------------------------------------------------------------------
    # Reward hooks -- Person B (Task #10) replaces both of these.
    # Placeholder implementations now so the env runs end-to-end.
    # ------------------------------------------------------------------

    def _score_step(self, action: CloudSecAction, observation_type: str, tool_data: dict | None) -> float:
        """Step-level reward shim. Returns 0.0 for now. Replaced by reward scorer module."""
        return 0.0

    def _score_terminal(self, root_cause: str, fix: str) -> tuple[float, dict]:
        """
        Terminal reward shim. Implements the simple rubric from ground_truth.yaml
        using string-match heuristics. Person B's reward scorer replaces this with
        a proper (possibly LLM-judged) implementation.
        """
        gt = self._store.ground_truth
        rubric_root = gt.get("reward_rubric", {}).get("root_cause_components", {})
        rubric_fix = gt.get("reward_rubric", {}).get("fix_components", {})

        root_lc = (root_cause or "").lower()
        fix_lc = (fix or "").lower()

        def has_any(text: str, needles: list[str]) -> bool:
            return any(n.lower() in text for n in needles)

        checks: dict[str, tuple[float, bool]] = {}

        # Root-cause checks
        if "identify_chg_1891" in rubric_root:
            checks["identify_chg_1891"] = (
                rubric_root["identify_chg_1891"]["weight"],
                "chg-1891" in root_lc,
            )
        if "identify_cloud2_scope" in rubric_root:
            checks["identify_cloud2_scope"] = (
                rubric_root["identify_cloud2_scope"]["weight"],
                "cloud-2" in root_lc,
            )
        if "identify_state_lock_mechanism" in rubric_root:
            checks["identify_state_lock_mechanism"] = (
                rubric_root["identify_state_lock_mechanism"]["weight"],
                has_any(root_lc, ["state lock", "state-lock", "silent failure", "concurrent"]),
            )
        if "identify_stale_key_symptom" in rubric_root:
            checks["identify_stale_key_symptom"] = (
                rubric_root["identify_stale_key_symptom"]["weight"],
                has_any(root_lc, ["old public key", "stale public key", "signature verification", "kid"]),
            )

        # Fix checks
        if "proposes_targeted_reapply" in rubric_fix:
            checks["proposes_targeted_reapply"] = (
                rubric_fix["proposes_targeted_reapply"]["weight"],
                (has_any(fix_lc, ["re-apply", "reapply", "apply"]) and "cloud-2" in fix_lc),
            )
        if "avoids_global_rollback" in rubric_fix:
            checks["avoids_global_rollback"] = (
                rubric_fix["avoids_global_rollback"]["weight"],
                not _advocates_rollback(fix_lc),
            )

        breakdown = {
            name: {"weight": weight, "hit": hit}
            for name, (weight, hit) in checks.items()
        }
        total = sum(weight for (weight, hit) in checks.values() if hit)
        # Clamp to [0, 1] just in case weights drift.
        total = max(0.0, min(1.0, total))
        return total, breakdown

    # ------------------------------------------------------------------
    # Trajectory logging (for reward scorer + analysis)
    # ------------------------------------------------------------------

    def _log_trajectory(
        self,
        action: CloudSecAction | None,
        observation_type: str,
        content: str,
        tool_data: dict | None = None,
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
            "tool_data_keys": list((tool_data or {}).keys()) if tool_data else [],
        }
        self._trajectory.append(entry)
