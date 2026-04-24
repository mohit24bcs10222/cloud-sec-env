# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Cloud Sec Env Environment Implementation — STUB.

Wires the new CloudSecAction / CloudSecObservation contract into the
OpenEnv server framework so HTTP plumbing can be smoke-tested. Real tool
logic (logs_search, trace_get, ...) is filled in during P1.
"""

from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import CloudSecAction, CloudSecObservation
except ImportError:
    from models import CloudSecAction, CloudSecObservation


# Max tool calls per episode before forced termination.
MAX_STEPS = 30

# Stub alert used until Task #1 data is authored.
STUB_ALERT = (
    "ALERT auth_svc_5xx_rate_cloud2\n"
    "SEV-2 fired 2026-04-22 14:02 UTC\n"
    "CONDITION HTTP 5xx rate on auth-svc in cloud-2 > 5% for 30min\n"
    "CURRENT 8.7%\n"
    "RUNBOOK kb://runbooks/auth-svc-5xx\n"
    "(STUB -- real alert lives in Task #1 data, coming in P1.)"
)


class CloudSecEnvironment(Environment):
    """Cloud Sec incident-investigation environment — stub shell."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)

    def reset(self) -> CloudSecObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        return CloudSecObservation(
            content=STUB_ALERT,
            data={"stub": True},
            observation_type="alert",
            steps_remaining=MAX_STEPS,
            done=False,
            reward=0.0,
            metadata={"episode_id": self._state.episode_id},
        )

    def step(self, action: CloudSecAction) -> CloudSecObservation:  # type: ignore[override]
        self._state.step_count += 1
        steps_remaining = max(0, MAX_STEPS - self._state.step_count)

        if action.tool_name == "submit_answer":
            return CloudSecObservation(
                content=(
                    "STUB evaluation:\n"
                    f"  submitted root_cause = {action.arguments.get('root_cause', '<missing>')}\n"
                    f"  submitted fix        = {action.arguments.get('fix', '<missing>')}\n"
                    "(Real scoring wired up in P1.)"
                ),
                data={"submitted": action.arguments},
                observation_type="evaluation",
                steps_remaining=steps_remaining,
                done=True,
                reward=0.0,
                metadata={"stub": True},
            )

        if steps_remaining == 0:
            return CloudSecObservation(
                content="Step budget exhausted. Episode terminated without an answer.",
                data={},
                observation_type="error",
                steps_remaining=0,
                done=True,
                reward=0.0,
                metadata={"reason": "out_of_steps"},
            )

        return CloudSecObservation(
            content=(
                f"STUB tool result:\n"
                f"  tool_name = {action.tool_name}\n"
                f"  arguments = {action.arguments}\n"
                "(Real tool logic wired up in P1.)"
            ),
            data={"stub": True, "echoed": {"tool_name": action.tool_name, "arguments": action.arguments}},
            observation_type="tool_result",
            steps_remaining=steps_remaining,
            done=False,
            reward=0.0,
            metadata={},
        )

    @property
    def state(self) -> State:
        return self._state
