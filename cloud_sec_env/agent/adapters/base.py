# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Abstract adapter interface.

An adapter wraps one LLM backend (Anthropic, Unsloth-Qwen, etc.) behind a
uniform `get_action / observe` interface so the RolloutHarness doesn't
care which model is driving.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ...models import CloudSecAction


class BaseAdapter(ABC):
    """Abstract model adapter."""

    model_name: str = "unknown"
    temperature: float = 0.0

    @abstractmethod
    def reset(self, initial_observation: str) -> None:
        """Start a new episode. `initial_observation` is the alert text from env.reset()."""

    @abstractmethod
    def get_action(self) -> Optional[CloudSecAction]:
        """Produce the next action given the conversation so far.

        Returns None if the adapter cannot produce a valid action
        (e.g., LLM emitted pure text with no tool_use, model refused, etc.).
        The harness treats a None return as a clean termination.
        """

    @abstractmethod
    def observe(self, content: str, observation_type: str) -> None:
        """Feed the env's response (observation) back into the adapter's state
        so the next get_action() call sees it."""
