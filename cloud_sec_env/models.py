# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for the Cloud Sec Env Environment.

Action / Observation contracts the agent and env exchange over HTTP/WebSocket.
"""

from typing import Any, Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class CloudSecAction(Action):
    """What the agent emits at each step.

    Unified shape for both tool calls and final-answer submission. When
    tool_name == "submit_answer", the episode terminates and terminal reward
    is computed against ground truth. Otherwise, the named tool runs and a
    `tool_result` observation is returned.
    """

    tool_name: str = Field(
        ...,
        description=(
            "One of the registered tool names "
            "(logs_search, trace_get, metric_query, ticket_search, slack_search, kb_search) "
            "or 'submit_answer' to terminate the episode."
        ),
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Per-tool arguments. Schema is validated server-side based on tool_name. "
            "For submit_answer, expects keys: 'root_cause' and 'fix'."
        ),
    )
    reasoning: Optional[str] = Field(
        default=None,
        description=(
            "Optional chain-of-thought the agent used to pick this action. "
            "Logged with the trajectory. NOT used for reward scoring."
        ),
    )


class CloudSecObservation(Observation):
    """What the agent sees at each step.

    Inherits `done`, `reward`, and `metadata` from the base Observation.
    """

    content: str = Field(
        ...,
        description=(
            "Human-readable text the agent reads. On reset: the incident alert. "
            "On step: formatted tool output, an error message, or the evaluation summary."
        ),
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Structured mirror of `content` (raw log rows, trace JSON, etc.). "
            "Not shown to the agent; used by the reward scorer and trajectory logger."
        ),
    )
    observation_type: str = Field(
        ...,
        description=(
            "One of: 'alert' (from reset), 'tool_result' (valid tool call), "
            "'error' (malformed action), 'evaluation' (terminal after submit_answer)."
        ),
    )
    steps_remaining: int = Field(
        ...,
        description=(
            "Steps left before forced termination. Agent can ration investigation depth."
        ),
    )
