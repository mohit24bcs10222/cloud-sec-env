# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Anthropic adapter -- wraps Claude tool-use API for our env."""

from __future__ import annotations

import os
from typing import Optional

from anthropic import Anthropic

from ...models import CloudSecAction
from ..tool_specs import ANTHROPIC_TOOLS, SYSTEM_PROMPT
from .base import BaseAdapter


class AnthropicAdapter(BaseAdapter):
    """Drives our env using Anthropic's native tool_use API."""

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        api_key: Optional[str] = None,
        system_prompt: str = SYSTEM_PROMPT,
        verbose: bool = False,
    ):
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.verbose = verbose

        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._messages: list[dict] = []
        self._pending_tool_use_id: Optional[str] = None

    # ------------------------------------------------------------------
    # BaseAdapter API
    # ------------------------------------------------------------------

    def reset(self, initial_observation: str) -> None:
        self._messages = [{"role": "user", "content": initial_observation}]
        self._pending_tool_use_id = None

    def get_action(self) -> Optional[CloudSecAction]:
        kwargs: dict = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "system": self.system_prompt,
            "tools": ANTHROPIC_TOOLS,
            # Force sequential tool use: our env is episode-based, one action per step.
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
            "messages": self._messages,
        }
        # Some newer Anthropic models (opus-4-7) reject the `temperature` arg.
        # Omit it for those; pass through for everyone else.
        if "opus-4-7" not in self.model_name:
            kwargs["temperature"] = self.temperature
        response = self._client.messages.create(**kwargs)

        # Serialize the assistant response to plain dicts so we can round-trip
        # it back into the next messages.create() without pydantic-object quirks.
        assistant_blocks: list[dict] = []
        reasoning_parts: list[str] = []
        tool_use = None
        for block in response.content:
            if block.type == "text":
                assistant_blocks.append({"type": "text", "text": block.text})
                reasoning_parts.append(block.text)
            elif block.type == "tool_use":
                assistant_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": dict(block.input),
                    }
                )
                tool_use = block
        self._messages.append({"role": "assistant", "content": assistant_blocks})

        if self.verbose:
            if reasoning_parts:
                print("[assistant-text] " + " ".join(reasoning_parts)[:200])
            if tool_use:
                print(f"[tool_use] {tool_use.name}({dict(tool_use.input)})")

        if tool_use is None:
            # Claude stopped without calling a tool. Treat as clean termination.
            return None

        self._pending_tool_use_id = tool_use.id
        reasoning = " ".join(reasoning_parts).strip() or None

        return CloudSecAction(
            tool_name=tool_use.name,
            arguments=dict(tool_use.input),
            reasoning=reasoning,
        )

    def observe(self, content: str, observation_type: str) -> None:
        if self._pending_tool_use_id is None:
            # Shouldn't happen in normal flow, but be defensive.
            self._messages.append({"role": "user", "content": content})
            return

        is_error = observation_type == "error"
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": self._pending_tool_use_id,
                        "content": content,
                        "is_error": is_error,
                    }
                ],
            }
        )
        self._pending_tool_use_id = None
