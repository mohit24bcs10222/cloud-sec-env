# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Loads task fixture data from disk into memory, lazily and cached.

One DataStore instance per episode/environment. Files are small (< 1 MB total)
so everything stays resident.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml


# Root of this package's data directory. Resolved once at import.
_THIS_DIR = Path(__file__).resolve().parent
_DATA_ROOT = _THIS_DIR.parent / "data"


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from markdown body. Returns (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip()
    return meta, body


class DataStore:
    """Lazy, cached in-memory view of one task's fixture data."""

    def __init__(self, task_id: str = "task_01_oidc_rotation"):
        self.task_id = task_id
        self.task_dir = _DATA_ROOT / task_id
        if not self.task_dir.exists():
            raise FileNotFoundError(f"Task data dir not found: {self.task_dir}")

    # ---- Alert ----
    @cached_property
    def alert(self) -> dict[str, Any]:
        return json.loads((self.task_dir / "alert.json").read_text(encoding="utf-8"))

    @cached_property
    def alert_time(self) -> datetime:
        """The moment T+0 -- every relative time_range is anchored here."""
        raw = self.alert["fired_at"]
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))

    # ---- Ground truth (reward scorer reads this, agent never sees it) ----
    @cached_property
    def ground_truth(self) -> dict[str, Any]:
        return yaml.safe_load((self.task_dir / "ground_truth.yaml").read_text(encoding="utf-8"))

    # ---- Tickets ----
    @cached_property
    def tickets(self) -> list[dict[str, Any]]:
        return yaml.safe_load((self.task_dir / "tickets.yaml").read_text(encoding="utf-8"))

    # ---- Slack messages ----
    @cached_property
    def slack(self) -> list[dict[str, Any]]:
        return yaml.safe_load((self.task_dir / "slack.yaml").read_text(encoding="utf-8"))

    # ---- Logs ----
    @cached_property
    def logs(self) -> list[dict[str, Any]]:
        path = self.task_dir / "logs.jsonl"
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    # ---- Traces ----
    @cached_property
    def traces(self) -> dict[str, dict[str, Any]]:
        return json.loads((self.task_dir / "traces.json").read_text(encoding="utf-8"))

    # ---- Metrics ----
    @cached_property
    def metrics(self) -> list[dict[str, Any]]:
        path = self.task_dir / "metrics.jsonl"
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    # ---- Knowledge base ----
    @cached_property
    def kb_docs(self) -> list[dict[str, Any]]:
        """
        Each doc: {id, path, title, last_edited (datetime), body_md, word_count, full_text}
        `full_text` is title + body (used for substring search).
        """
        docs = []
        for md_file in sorted((self.task_dir / "kb").glob("*.md")):
            raw = md_file.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(raw)
            word_count = len(body.split())
            last_edited_raw = meta.get("last_edited")
            last_edited = (
                datetime.fromisoformat(str(last_edited_raw).replace("Z", "+00:00"))
                if last_edited_raw
                else None
            )
            docs.append(
                {
                    "id": meta.get("id"),
                    "path": meta.get("path"),
                    "title": meta.get("title"),
                    "last_edited": last_edited,
                    "body_md": body,
                    "word_count": word_count,
                    "full_text": f"{meta.get('title', '')}\n\n{body}".lower(),
                }
            )
        return docs

    # ---- Helpers ----
    @staticmethod
    def parse_log_ts(row: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))

    @staticmethod
    def parse_metric_ts(row: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(row["t"].replace("Z", "+00:00"))

    @staticmethod
    def parse_slack_ts(row: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))

    @staticmethod
    def parse_ticket_ts(row: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(row["created"].replace("Z", "+00:00"))
