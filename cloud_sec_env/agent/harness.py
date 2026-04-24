# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Rollout harness -- drives an LLM through one episode of the env.

Usage:
    from cloud_sec_env.agent.adapters.anthropic_adapter import AnthropicAdapter
    from cloud_sec_env.agent.harness import RolloutHarness

    harness = RolloutHarness(AnthropicAdapter(model="claude-opus-4-7"))
    trajectory = harness.run_episode()
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..server.cloud_sec_env_environment import CloudSecEnvironment
from .adapters.base import BaseAdapter


class RolloutHarness:
    """Runs one LLM through one episode of the env, records the trajectory."""

    def __init__(
        self,
        adapter: BaseAdapter,
        task_id: str = "task_01_oidc_rotation",
        max_steps: int = 30,
        verbose: bool = False,
    ):
        self.adapter = adapter
        self.task_id = task_id
        self.max_steps = max_steps
        self.verbose = verbose

    def run_episode(self) -> dict[str, Any]:
        env = CloudSecEnvironment(task_id=self.task_id)
        obs = env.reset()
        self.adapter.reset(obs.content)

        started_at = datetime.now(timezone.utc).isoformat()
        started_mono = time.monotonic()

        steps: list[dict[str, Any]] = []
        total_reward = 0.0
        terminal_reward: float | None = None
        terminated_cleanly = False
        stop_reason = "budget_exhausted"

        if self.verbose:
            print(f"[harness] episode start -- task={self.task_id} model={self.adapter.model_name}")
            print(f"[harness] ALERT:\n{obs.content}\n")

        for step_num in range(1, self.max_steps + 1):
            try:
                action = self.adapter.get_action()
            except Exception as e:
                stop_reason = f"adapter_error: {type(e).__name__}: {e}"
                if self.verbose:
                    print(f"[harness] adapter error: {e}")
                break

            if action is None:
                stop_reason = "adapter_returned_none"
                if self.verbose:
                    print("[harness] adapter returned None -- stopping.")
                break

            if self.verbose:
                print(f"[harness] step {step_num}: {action.tool_name}({action.arguments})")

            result = env.step(action)
            step_reward = result.reward if result.reward is not None else 0.0
            total_reward += step_reward

            steps.append(
                {
                    "step": step_num,
                    "action": {
                        "tool_name": action.tool_name,
                        "arguments": action.arguments,
                        "reasoning": action.reasoning,
                    },
                    "observation_type": result.observation_type,
                    "content": result.content,
                    "reward": step_reward,
                    "step_hits": result.metadata.get("step_reward_hits", []),
                    "steps_remaining": result.steps_remaining,
                    "done": result.done,
                }
            )

            if self.verbose:
                hits = result.metadata.get("step_reward_hits", [])
                print(f"[harness]   -> {result.observation_type}  reward={step_reward:+.2f}  hits={hits}")

            # Feed the response back to the adapter so next get_action() sees it.
            self.adapter.observe(result.content, result.observation_type)

            if result.done:
                terminal_reward = step_reward
                terminated_cleanly = action.tool_name == "submit_answer"
                stop_reason = "done" if terminated_cleanly else f"terminated:{result.observation_type}"
                break

        duration_s = time.monotonic() - started_mono

        return {
            "task_id": self.task_id,
            "model": self.adapter.model_name,
            "temperature": self.adapter.temperature,
            "started_at": started_at,
            "duration_s": round(duration_s, 2),
            "stop_reason": stop_reason,
            "terminated_cleanly": terminated_cleanly,
            "num_steps": len(steps),
            "total_reward": round(total_reward, 4),
            "terminal_reward": terminal_reward,
            "steps": steps,
        }
