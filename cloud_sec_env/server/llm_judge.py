# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
LLM-as-judge terminal reward scorer.

Instead of keyword-matching, we use Claude Sonnet to grade each submit_answer
on a 0.0-1.0 scale per rubric dimension. This:
  - Handles nuance (vague answers score partially, not binary fail)
  - Catches verbose-but-missing-the-point answers that keyword match lets through
  - Scores two extra innovation dimensions: evidence citation and
    red-herring falsification
  - Produces justifications alongside scores (useful for debugging + demo)

One Sonnet call per episode at ~2-3s latency and ~$0.02/call. Keyword rubric
remains available as a fast fallback via RewardScorer(use_llm_judge=False).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from anthropic import Anthropic


JUDGE_MODEL_DEFAULT = "claude-sonnet-4-6"


JUDGE_PROMPT_TEMPLATE = """You are grading an SRE's post-incident analysis against a known ground truth.

## Ground truth (what actually happened)

The incident: an OIDC signing key rotation (CHG-1891, applied by SRE j.patel) was
pushed via Terraform to all 3 clouds. In cloud-2, a concurrent Terraform run by
engineer m.chen held the state lock, causing j.patel's apply to silently fail
with warnings (no new key pushed to cloud-2 sts-broker). The Okta side rotated
the signing key anyway, so new JWTs are signed with kid=rsa-2026-q2 but cloud-2's
sts-broker still only has kid=rsa-2025-q4, causing every Acme JWT to fail
signature verification. cloud-1 and cloud-3 received the rotation cleanly and
are healthy. The Acme tenant is hit because their traffic geographically routes
to cloud-2.

The correct fix is a targeted re-apply of Terraform for cloud-2 only
(e.g. `terraform apply -target=module.cloud_2.sts_broker_keys`).
A GLOBAL rollback of the rotation is WRONG because it would break cloud-1 and
cloud-3 which are healthy on the new key.

Red herrings the agent should NOT blame:
- INC-4470 cloud-3 ml-scorer CPU throttling (unrelated workload issue)
- CHG-1895 cloud-1 policy-svc v2.14.3 routine deploy
- kb-09 stale 2024 auth-outage retro doc

## Submitted answer

ROOT CAUSE:
{root_cause}

FIX:
{fix}

## Scoring

Score each dimension on a 0.0-1.0 scale:
- 0.0 = wrong or missed
- 0.3-0.6 = partially correct / vague / half the point
- 0.7-0.9 = mostly correct with minor omissions
- 1.0 = clearly and specifically correct

### Core rubric (6 dimensions, weighted)

1. **identify_chg_1891** (weight 0.25): Does the answer name CHG-1891 AND identify j.patel as the engineer who applied it? Score 1.0 only if BOTH are present. 0.5 if only one.
2. **identify_cloud2_scope** (weight 0.15): Does the answer correctly scope the issue to cloud-2, with awareness that cloud-1 and cloud-3 are healthy (either explicitly or by recommending not to touch them)?
3. **identify_state_lock_mechanism** (weight 0.20): Does the answer explain that a concurrent Terraform run (by m.chen or from #infra-terraform) caused a state-lock contention that made the apply silently fail on cloud-2? The MECHANISM must be clear, not just "something went wrong with terraform".
4. **identify_stale_key_symptom** (weight 0.15): Does the answer connect the JWT signature-verification failure (kid=rsa-2026-q2 unknown) to cloud-2's sts-broker still holding the STALE public key (rsa-2025-q4)?
5. **proposes_targeted_reapply** (weight 0.15): Does the fix propose a TARGETED Terraform re-apply for cloud-2 only (not global)? Score 1.0 for explicit target; 0.3 for generic "redeploy"; 0.0 if no reapply mentioned.
6. **avoids_global_rollback** (weight 0.10): Does the fix AVOID advocating a global rollback? Score 1.0 if rollback is not mentioned OR is explicitly rejected. 0.0 if the fix recommends rolling back the global rotation.

### Innovation bonuses (2 dimensions, stackable up to +0.1)

7. **cites_specific_evidence** (bonus weight 0.05): Does the answer cite 3+ specific pieces of evidence (ticket IDs like CHG-1891, kid names like rsa-2026-q2, specific timestamps, trace IDs, Slack channel names)? Score 1.0 for 3+ citations, 0.5 for 1-2, 0.0 for none.
8. **falsifies_red_herrings** (bonus weight 0.05): Does the answer explicitly rule out any red herring (cloud-3 CPU, cloud-1 policy-svc deploy, stale 2024 doc) as unrelated? Score 1.0 if at least one is explicitly falsified, 0.0 otherwise.

## Output format

Return ONLY a JSON object of this exact shape. NO prose, NO markdown fences, NO explanation outside the JSON:

{{
  "scores": {{
    "identify_chg_1891": 0.0,
    "identify_cloud2_scope": 0.0,
    "identify_state_lock_mechanism": 0.0,
    "identify_stale_key_symptom": 0.0,
    "proposes_targeted_reapply": 0.0,
    "avoids_global_rollback": 0.0,
    "cites_specific_evidence": 0.0,
    "falsifies_red_herrings": 0.0
  }},
  "justifications": {{
    "identify_chg_1891": "brief sentence",
    "identify_cloud2_scope": "brief sentence",
    "identify_state_lock_mechanism": "brief sentence",
    "identify_stale_key_symptom": "brief sentence",
    "proposes_targeted_reapply": "brief sentence",
    "avoids_global_rollback": "brief sentence",
    "cites_specific_evidence": "brief sentence",
    "falsifies_red_herrings": "brief sentence"
  }}
}}
"""


class LLMJudge:
    """Sonnet-graded terminal scorer."""

    CORE_WEIGHTS: dict[str, float] = {
        "identify_chg_1891": 0.25,
        "identify_cloud2_scope": 0.15,
        "identify_state_lock_mechanism": 0.20,
        "identify_stale_key_symptom": 0.15,
        "proposes_targeted_reapply": 0.15,
        "avoids_global_rollback": 0.10,
    }
    BONUS_WEIGHTS: dict[str, float] = {
        "cites_specific_evidence": 0.05,
        "falsifies_red_herrings": 0.05,
    }

    def __init__(
        self,
        model: str = JUDGE_MODEL_DEFAULT,
        api_key: Optional[str] = None,
        max_tokens: int = 2048,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def grade(self, root_cause: str, fix: str) -> dict[str, Any]:
        """Grade one submit_answer. Returns a structured result."""
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            root_cause=root_cause or "(no root_cause provided)",
            fix=fix or "(no fix provided)",
        )

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            return self._failure_result(f"Judge API call failed: {type(e).__name__}: {e}")

        raw_text = "".join(
            block.text for block in response.content if block.type == "text"
        )

        parsed = self._extract_json(raw_text)
        if parsed is None or "scores" not in parsed:
            return self._failure_result(f"Judge returned unparseable JSON: {raw_text[:300]}")

        raw_scores = parsed.get("scores", {}) or {}
        justifications = parsed.get("justifications", {}) or {}

        core_score = 0.0
        bonus_score = 0.0
        breakdown: dict[str, dict[str, Any]] = {}

        for name, weight in self.CORE_WEIGHTS.items():
            s = _clamp01(raw_scores.get(name, 0.0))
            weighted = s * weight
            core_score += weighted
            breakdown[name] = {
                "weight": weight,
                "score": round(s, 3),
                "weighted": round(weighted, 3),
                "justification": justifications.get(name, ""),
                "bonus": False,
            }

        for name, weight in self.BONUS_WEIGHTS.items():
            s = _clamp01(raw_scores.get(name, 0.0))
            weighted = s * weight
            bonus_score += weighted
            breakdown[name] = {
                "weight": weight,
                "score": round(s, 3),
                "weighted": round(weighted, 3),
                "justification": justifications.get(name, ""),
                "bonus": True,
            }

        total = min(1.0, core_score + bonus_score)
        return {
            "total": round(total, 3),
            "core_score": round(core_score, 3),
            "bonus_score": round(bonus_score, 3),
            "breakdown": breakdown,
            "judge_model": self.model,
            "judge_error": None,
        }

    def _failure_result(self, err: str) -> dict[str, Any]:
        return {
            "total": 0.0,
            "core_score": 0.0,
            "bonus_score": 0.0,
            "breakdown": {},
            "judge_model": self.model,
            "judge_error": err,
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        if not text:
            return None
        text = text.strip()
        if text.startswith("```"):
            nl = text.find("\n")
            if nl >= 0:
                text = text[nl + 1:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
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
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        return None
                    break
        return None


def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v
