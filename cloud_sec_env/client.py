# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Cloud Sec Env Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import CloudSecAction, CloudSecObservation


class CloudSecEnv(EnvClient[CloudSecAction, CloudSecObservation, State]):
    """Client for the Cloud Sec Env environment.

    Example:
        >>> with CloudSecEnv(base_url="http://localhost:8000") as client:
        ...     result = client.reset()
        ...     print(result.observation.content)
        ...
        ...     result = client.step(CloudSecAction(
        ...         tool_name="logs_search",
        ...         arguments={"cloud": "cloud-2", "service": "auth-svc"},
        ...     ))
        ...     print(result.observation.content)
    """

    def _step_payload(self, action: CloudSecAction) -> Dict:
        return {
            "tool_name": action.tool_name,
            "arguments": action.arguments,
            "reasoning": action.reasoning,
        }

    def _parse_result(self, payload: Dict) -> StepResult[CloudSecObservation]:
        obs_data = payload.get("observation", {})
        observation = CloudSecObservation(
            content=obs_data.get("content", ""),
            data=obs_data.get("data", {}),
            observation_type=obs_data.get("observation_type", "tool_result"),
            steps_remaining=obs_data.get("steps_remaining", 0),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
