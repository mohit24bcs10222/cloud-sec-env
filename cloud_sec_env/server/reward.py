# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Reward scoring for the Cloud Sec Env.

Two distinct reward streams, both read from `ground_truth.yaml`:

1. Step-level rewards: small (+/-) bumps on each tool call based on
   investigative quality (correct scoping, good pivots, avoiding herrings).
   This is what gives training a dense learning signal instead of a single
   terminal pass/fail.

2. Terminal reward: a 0..1 score computed on submit_answer against the
   root_cause / fix rubric in ground_truth.yaml.

One RewardScorer instance per episode (reset() at episode start).
"""

from __future__ import annotations

import re
from typing import Any, Optional

try:
    from .llm_judge import LLMJudge
except ImportError:
    LLMJudge = None  # type: ignore


# ----------------------------------------------------------------------
# Shared text helpers (mirror the tool-side ones; kept duplicated to
# avoid cross-module import cycles)
# ----------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[-_/]", " ", (text or "").lower())


def _has_any(text: str, needles: list[str]) -> bool:
    t = text.lower()
    return any(n.lower() in t for n in needles)


def _advocates_rollback(fix_lc: str) -> bool:
    """True iff the fix appears to recommend a global rollback
    (rollback mention without a nearby negation like 'do not')."""
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


# ----------------------------------------------------------------------
# RewardScorer
# ----------------------------------------------------------------------

class RewardScorer:
    """Per-episode stateful scorer. Tracks which step-level achievements
    have been earned (one-shot) plus some running counters."""

    def __init__(
        self,
        ground_truth: dict[str, Any],
        judge: "Optional[LLMJudge]" = None,
    ):
        """If `judge` is provided, score_terminal uses the LLM judge rubric.
        Otherwise it falls back to the deterministic keyword rubric."""
        self.gt = ground_truth
        self.judge = judge
        self.reset()

    # --- Lifecycle ---

    def reset(self) -> None:
        """Clear all per-episode state. Call at episode start."""
        self.step_num: int = 0
        self.seen_trace_ids: set[str] = set()      # trace_ids surfaced by logs_search
        self.achievements: set[str] = set()        # one-shot achievements earned
        self.cloud3_streak: int = 0                # consecutive cloud-3-scoped calls
        self.total_step_reward: float = 0.0        # accumulated step reward this episode

    # --- Step-level scoring ---

    def score_step(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        observation_type: str,
        tool_data: dict[str, Any] | None,
    ) -> tuple[float, list[str]]:
        """
        Score one step. Returns (reward_delta, list_of_triggered_signal_names).

        Called AFTER the tool has run, so tool_data contains the result.
        For error observations tool_data is None.
        """
        self.step_num += 1
        delta = 0.0
        hits: list[str] = []

        # Track trace_ids the agent has observed in logs — used by
        # `pivots_to_trace` to reward a log->trace pivot.
        if tool_name == "logs_search" and tool_data:
            for row in tool_data.get("rows", []) or []:
                tid = row.get("trace_id")
                if tid:
                    self.seen_trace_ids.add(tid)

        # Maintain cloud-3 streak counter.
        cloud_arg = arguments.get("cloud")
        if cloud_arg == "cloud-3":
            self.cloud3_streak += 1
        else:
            self.cloud3_streak = 0

        step_rewards_cfg = self.gt.get("step_rewards", {})

        # --- correct_first_tool ---
        if (
            "correct_first_tool" in step_rewards_cfg
            and "correct_first_tool" not in self.achievements
            and self.step_num == 1
            and tool_name in ("logs_search", "trace_search")
            and arguments.get("cloud") == "cloud-2"
        ):
            w = step_rewards_cfg["correct_first_tool"]["weight"]
            delta += w
            hits.append("correct_first_tool")
            self.achievements.add("correct_first_tool")

        # --- finds_signature_error_log ---
        if (
            "finds_signature_error_log" in step_rewards_cfg
            and "finds_signature_error_log" not in self.achievements
            and tool_name == "logs_search"
            and tool_data
        ):
            for row in tool_data.get("rows", []) or []:
                msg = row.get("message", "")
                if "signature verification" in msg.lower() or "kid_mismatch" in msg.lower():
                    w = step_rewards_cfg["finds_signature_error_log"]["weight"]
                    delta += w
                    hits.append("finds_signature_error_log")
                    self.achievements.add("finds_signature_error_log")
                    break

        # --- pivots_to_trace ---
        if (
            "pivots_to_trace" in step_rewards_cfg
            and "pivots_to_trace" not in self.achievements
            and tool_name == "trace_get"
            and observation_type == "tool_result"
        ):
            tid = arguments.get("trace_id")
            if tid and tid in self.seen_trace_ids:
                w = step_rewards_cfg["pivots_to_trace"]["weight"]
                delta += w
                hits.append("pivots_to_trace")
                self.achievements.add("pivots_to_trace")

        # --- finds_chg_1891_ticket ---
        if (
            "finds_chg_1891_ticket" in step_rewards_cfg
            and "finds_chg_1891_ticket" not in self.achievements
            and tool_name == "ticket_search"
            and tool_data
        ):
            for t in tool_data.get("tickets", []) or []:
                if t.get("id") == "CHG-1891":
                    w = step_rewards_cfg["finds_chg_1891_ticket"]["weight"]
                    delta += w
                    hits.append("finds_chg_1891_ticket")
                    self.achievements.add("finds_chg_1891_ticket")
                    break

        # --- reads_state_lock_slack ---
        if (
            "reads_state_lock_slack" in step_rewards_cfg
            and "reads_state_lock_slack" not in self.achievements
            and tool_name == "slack_search"
            and tool_data
        ):
            for m in tool_data.get("messages", []) or []:
                if (
                    m.get("channel") == "#infra-terraform"
                    and "state" in _normalize(m.get("text", ""))
                    and "lock" in _normalize(m.get("text", ""))
                ):
                    w = step_rewards_cfg["reads_state_lock_slack"]["weight"]
                    delta += w
                    hits.append("reads_state_lock_slack")
                    self.achievements.add("reads_state_lock_slack")
                    break

        # --- finds_correct_runbook ---
        if (
            "finds_correct_runbook" in step_rewards_cfg
            and "finds_correct_runbook" not in self.achievements
            and tool_name == "kb_search"
            and tool_data
        ):
            for doc in tool_data.get("docs", []) or []:
                if doc.get("id") == "kb-42":
                    w = step_rewards_cfg["finds_correct_runbook"]["weight"]
                    delta += w
                    hits.append("finds_correct_runbook")
                    self.achievements.add("finds_correct_runbook")
                    break

        # --- penalty_no_scoping ---
        # Not one-shot: applies each time the agent calls logs_search with no scope.
        if (
            "penalty_no_scoping" in step_rewards_cfg
            and tool_name == "logs_search"
            and not arguments.get("cloud")
            and not arguments.get("service")
        ):
            w = step_rewards_cfg["penalty_no_scoping"]["weight"]
            delta += w
            hits.append("penalty_no_scoping")

        # --- penalty_cloud3_fixation ---
        # Applies once when the streak crosses the threshold, then again if it
        # rebuilds (rare). Keeps the same achievement lock to avoid runaway penalty.
        if (
            "penalty_cloud3_fixation" in step_rewards_cfg
            and "penalty_cloud3_fixation" not in self.achievements
            and self.cloud3_streak >= 3
        ):
            w = step_rewards_cfg["penalty_cloud3_fixation"]["weight"]
            delta += w
            hits.append("penalty_cloud3_fixation")
            self.achievements.add("penalty_cloud3_fixation")

        self.total_step_reward += delta
        return delta, hits

    # --- Terminal scoring ---

    def score_terminal(
        self,
        root_cause: str,
        fix: str,
        trajectory: "Optional[list[dict]]" = None,
    ) -> tuple[float, dict[str, dict[str, Any]]]:
        """Score the final submit_answer.

        If an LLM judge was provided at construction, use it (trajectory-aware
        continuous 0-1 per dimension + bonus dimensions). Otherwise fall back
        to the deterministic keyword rubric.
        """
        if self.judge is not None:
            result = self.judge.grade(root_cause, fix, trajectory=trajectory)
            breakdown = dict(result.get("breakdown", {}))
            if result.get("judge_error"):
                breakdown["_judge_error"] = {"weight": 0.0, "hit": False, "reason": result["judge_error"]}
            return result["total"], breakdown

        # ---- Fallback: keyword rubric ----
        rubric = self.gt.get("reward_rubric", {})
        rubric_root = rubric.get("root_cause_components", {}) or {}
        rubric_fix = rubric.get("fix_components", {}) or {}

        root_lc = (root_cause or "").lower()
        fix_lc = (fix or "").lower()

        checks: dict[str, tuple[float, bool]] = {}

        # --- Root-cause (STRICT: compound conditions, not keyword soup) ---

        # (1) identify_chg_1891 -- requires BOTH the ticket ID and the engineer name.
        # "Something about CHG-1891" isn't enough; must show they saw who applied it.
        if "identify_chg_1891" in rubric_root:
            checks["identify_chg_1891"] = (
                rubric_root["identify_chg_1891"]["weight"],
                "chg-1891" in root_lc and "j.patel" in root_lc,
            )

        # (2) identify_cloud2_scope -- "cloud-2" alone isn't enough. Agent must show
        # scope discipline: EITHER say "cloud-2 only" explicitly OR acknowledge that
        # cloud-1 and cloud-3 are healthy (proving they thought about all three clouds).
        if "identify_cloud2_scope" in rubric_root:
            scope_ok = "cloud-2" in root_lc and (
                "cloud-2 only" in root_lc
                or "only cloud-2" in root_lc
                or "only affects cloud-2" in root_lc
                or ("cloud-1" in root_lc and "cloud-3" in root_lc)
            )
            checks["identify_cloud2_scope"] = (rubric_root["identify_cloud2_scope"]["weight"], scope_ok)

        # (3) identify_state_lock_mechanism -- must mention "state lock" AND either
        # name the contending engineer (m.chen) or explicitly say "concurrent".
        # Generic "silent failure" no longer counts on its own.
        if "identify_state_lock_mechanism" in rubric_root:
            mentions_state_lock = "state lock" in root_lc or "state-lock" in root_lc
            mentions_contention = "m.chen" in root_lc or "concurrent" in root_lc
            checks["identify_state_lock_mechanism"] = (
                rubric_root["identify_state_lock_mechanism"]["weight"],
                mentions_state_lock and mentions_contention,
            )

        # (4) identify_stale_key_symptom -- must connect BOTH the rotation event
        # AND the signature-verification failure. Just saying "kid" isn't enough.
        if "identify_stale_key_symptom" in rubric_root:
            mentions_signature_failure = (
                "signature verification" in root_lc
                or "kid mismatch" in root_lc
                or "kid=" in root_lc
                or "kid unknown" in root_lc
            )
            mentions_rotation_context = (
                "rotation" in root_lc
                or "new key" in root_lc
                or "new public key" in root_lc
                or "old key" in root_lc
                or "stale key" in root_lc
                or "stale public key" in root_lc
                or "rsa-2026" in root_lc
            )
            checks["identify_stale_key_symptom"] = (
                rubric_root["identify_stale_key_symptom"]["weight"],
                mentions_signature_failure and mentions_rotation_context,
            )

        # --- Fix ---
        if "proposes_targeted_reapply" in rubric_fix:
            checks["proposes_targeted_reapply"] = (
                rubric_fix["proposes_targeted_reapply"]["weight"],
                (_has_any(fix_lc, ["re-apply", "reapply", "apply"]) and "cloud-2" in fix_lc),
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
        total = max(0.0, min(1.0, total))
        return total, breakdown

    # --- Snapshot ---

    def summary(self) -> dict[str, Any]:
        """Episode snapshot for trajectory logs / debugging."""
        return {
            "step_num": self.step_num,
            "total_step_reward": round(self.total_step_reward, 4),
            "achievements_earned": sorted(self.achievements),
            "seen_trace_ids": sorted(self.seen_trace_ids),
            "cloud3_streak": self.cloud3_streak,
        }
