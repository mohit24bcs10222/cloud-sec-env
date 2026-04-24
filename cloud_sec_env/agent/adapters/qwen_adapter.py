# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Qwen adapter using HuggingFace Inference API + prompted tool calling.

Instead of relying on provider-specific native tool-use APIs (which vary in
quality), we describe the tools in the system prompt and require Qwen to
respond with a strict JSON object. This is:
  - Robust across providers (HF Inference, Together, local vLLM, etc.)
  - Exactly the format we'll fine-tune Qwen on in Task #15 (no distribution
    shift between baseline eval and fine-tuned eval)
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from huggingface_hub import InferenceClient

from ...models import CloudSecAction
from ..tool_specs import ANTHROPIC_TOOLS
from ..tool_specs import SYSTEM_PROMPT as BASE_SYSTEM_PROMPT
from .base import BaseAdapter


def _format_tool_for_prompt(tool: dict) -> str:
    lines = [f"### {tool['name']}", tool["description"]]
    schema = tool.get("input_schema", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    if props:
        lines.append("Arguments:")
        for name, spec in props.items():
            req_marker = " (required)" if name in required else " (optional)"
            type_str = spec.get("type", "any")
            if "enum" in spec:
                type_str = f"one of {spec['enum']}"
            desc = spec.get("description", "")
            lines.append(f"  - {name}: {type_str}{req_marker}. {desc}")
    return "\n".join(lines)


_TOOL_SECTION = "\n\n".join(_format_tool_for_prompt(t) for t in ANTHROPIC_TOOLS)

QWEN_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT
    + "\n\n## Available tools\n\n"
    + _TOOL_SECTION
    + """

## Response format (STRICT)

Every one of your turns MUST be ONLY a valid JSON object of this exact shape:

{
  "reasoning": "<one or two sentences of your thinking, optional>",
  "tool_name": "<exact name of one tool from the list above>",
  "arguments": { <arguments for that tool; pass {} if none> }
}

Do NOT include any prose, explanation, or markdown fences outside the JSON.
Respond with a single JSON object and nothing else. The harness will parse your
response as JSON and fail the episode if it cannot.
"""
)


class QwenAdapter(BaseAdapter):
    """Drives our env using a prompt-based JSON protocol over the HF Inference API."""

    def __init__(
        self,
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        api_key: Optional[str] = None,
        provider: str = "auto",
        verbose: bool = False,
    ):
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.verbose = verbose

        self._client = InferenceClient(
            provider=provider,
            api_key=api_key or os.environ.get("HF_TOKEN"),
        )
        self._messages: list[dict] = []

    # ------------------------------------------------------------------
    # BaseAdapter API
    # ------------------------------------------------------------------

    def reset(self, initial_observation: str) -> None:
        self._messages = [{"role": "user", "content": initial_observation}]

    def get_action(self) -> Optional[CloudSecAction]:
        full_messages = [{"role": "system", "content": QWEN_SYSTEM_PROMPT}] + self._messages
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=full_messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        content = response.choices[0].message.content or ""

        # Record assistant text verbatim in history (mirrors what Qwen saw in-context).
        self._messages.append({"role": "assistant", "content": content})

        parsed = self._extract_json(content)
        if self.verbose:
            preview = content[:200].replace("\n", " ")
            print(f"[qwen-response] {preview}{'...' if len(content) > 200 else ''}")

        if parsed is None:
            if self.verbose:
                print("[qwen] failed to parse JSON from response -- stopping episode.")
            return None

        tool_name = parsed.get("tool_name")
        arguments = parsed.get("arguments")
        reasoning = parsed.get("reasoning")

        if not isinstance(tool_name, str) or not tool_name:
            if self.verbose:
                print("[qwen] parsed JSON missing tool_name -- stopping episode.")
            return None

        if not isinstance(arguments, dict):
            arguments = {}

        return CloudSecAction(
            tool_name=tool_name,
            arguments=arguments,
            reasoning=reasoning if isinstance(reasoning, str) else None,
        )

    def observe(self, content: str, observation_type: str) -> None:
        # Feed the env's response back as the next user message. Tag with the
        # observation type so Qwen knows error vs. tool_result.
        prefix = f"[{observation_type.upper()}]\n"
        self._messages.append({"role": "user", "content": prefix + content})

    # ------------------------------------------------------------------
    # JSON extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Best-effort extraction of a JSON object from model output."""
        if not text:
            return None
        text = text.strip()

        # Strip markdown fences if present.
        if text.startswith("```"):
            nl = text.find("\n")
            if nl >= 0:
                text = text[nl + 1:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # Try direct parse.
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        # Fallback: find the first {...} block. Greedy match of braces.
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        return None
                    break
        return None
