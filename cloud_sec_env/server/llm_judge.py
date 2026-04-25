# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
LLM-as-judge terminal reward scorer -- trajectory-aware.

Three distinguishing features that make this rubric hard to game:

1. EVIDENCE-SUPPORTED-CLAIMS scoring. The judge receives the agent's full
   trajectory (tool calls + results) alongside the submitted answer. It
   checks whether each factual claim in the answer is backed by something
   the agent actually observed. An agent that emits the correct answer
   without investigating (e.g., guesses from the system prompt alone)
   scores zero on this dimension. This forces grounded reasoning.

2. EXPLICIT-ELIMINATION scoring. The judge looks for the signature of
   senior-SRE thinking: explicitly identifying a plausible alternative
   hypothesis AND ruling it out with a specific reason. Simply naming the
   correct cause without excluding alternatives scores zero here.

3. CONTINUOUS 0-1 PER DIMENSION. Each of the 8 core + 1 bonus dimensions
   is graded continuously with a justification. Vague-but-correct answers
   lose partial credit; bullshit-sounding-but-unsupported answers lose more.

Cost: one Sonnet call per episode at ~$0.02-0.05/call.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from anthropic import Anthropic


JUDGE_MODEL_DEFAULT = "claude-sonnet-4-6"


JUDGE_PROMPT_TEMPLATE = """You are grading an SRE's post-incident analysis.
You must grade on what the agent ACTUALLY INVESTIGATED (trajectory) and SUBMITTED (answer),
NOT what an ideal SRE would have written.

## Ground truth (what actually happened)

The incident: an OIDC signing key rotation (CHG-1891, applied by SRE j.patel)
was pushed via Terraform to all 3 clouds. In cloud-2, a concurrent Terraform
run by engineer m.chen held the state lock, causing j.patel's apply to
silently complete with warnings -- the new public key was NOT written to
cloud-2's sts-broker. Okta rotated the signing key anyway, so new JWTs are
signed with kid=rsa-2026-q2 but cloud-2's sts-broker still only knows
kid=rsa-2025-q4. Every Acme JWT fails signature verification on cloud-2.
cloud-1 and cloud-3 received the rotation cleanly and are healthy.

Correct fix: targeted re-apply for cloud-2 only. A global rollback is WRONG
(breaks cloud-1 and cloud-3 which are healthy on the new key).

### The tempting WRONG hypothesis the agent might fall for: CHG-1888

CHG-1888 is a JWT claim-parser upgrade by the same author (j.patel), same
service (sts-broker), one day earlier. It produces benign WARN logs on
cloud-2 ("claim_parser: fallback to legacy format"). An agent might blame
CHG-1888 because of superficial match.

THE DISAMBIGUATING TEST: CHG-1888 shipped to cloud-1 AND cloud-2. If it were
the cause, cloud-1 would show matching failures. cloud-1 metrics are flat.
Therefore CHG-1888 CANNOT be the cause. Only CHG-1891 produces the
cloud-2-asymmetric behavior (state-lock silent fail on cloud-2 only).

### Other red herrings (lesser importance)

- INC-4470 cloud-3 ml-scorer CPU throttling (different cloud, different service)
- CHG-1895 cloud-1 policy-svc v2.14.3 routine deploy
- kb-09 stale 2024 auth-outage retro doc referencing retired library

## Agent's trajectory (tool calls made + key results observed)

{trajectory_summary}

## Submitted answer

ROOT CAUSE:
{root_cause}

FIX:
{fix}

## Scoring

Score each dimension 0.0 to 1.0 where:
- 0.0 = wrong or missed completely
- 0.3-0.6 = partially correct / vague / half right
- 0.7-0.9 = mostly correct with minor gaps
- 1.0 = clearly and specifically correct

### CORE rubric (8 dimensions, weights sum to 1.00)

1. **identify_chg_1891** (weight 0.15): Names CHG-1891 AND identifies j.patel. Both = 1.0; one = 0.5.
2. **identify_cloud2_scope** (weight 0.15): Scopes correctly to cloud-2 with awareness that cloud-1/cloud-3 are healthy.
3. **identify_state_lock_mechanism** (weight 0.20): Explains the concurrent-Terraform / state-lock silent-failure mechanism. Mechanism must be CLEAR, not just "something went wrong". Naming m.chen or #infra-terraform strengthens the score.
4. **identify_stale_key_symptom** (weight 0.15): Connects the JWT signature failure (kid=rsa-2026-q2 unknown) to cloud-2 holding the stale public key (rsa-2025-q4).
5. **proposes_targeted_reapply** (weight 0.10): Proposes a TARGETED Terraform re-apply for cloud-2 only (not global). Specific targeting = 1.0; generic redeploy = 0.3.
6. **avoids_global_rollback** (weight 0.05): Does not advocate a global rollback (or explicitly rejects one).

7. **explicit_elimination** (weight 0.10): Does the answer explicitly identify at least one ALTERNATIVE hypothesis (CHG-1888, CHG-1895, cloud-3 CPU issue) AND rule it out with a specific reason? Score 1.0 for clear elimination with evidence ("CHG-1888 can't be the cause because it shipped to cloud-1 too and cloud-1 is healthy"). Score 0.5 for weak elimination ("CHG-1888 is probably unrelated"). Score 0.0 for no elimination at all. This dimension specifically catches whether the agent did the senior-SRE work of falsifying alternatives, not just pattern-matching the right answer.

8. **evidence_supported_claims** (weight 0.10): For each major factual claim in the submitted answer, is there a tool-call observation in the trajectory that supports it? Major claims include: "CHG-1891 applied by j.patel", "m.chen held state lock", "cloud-1 and cloud-3 are healthy", "kid=rsa-2026-q2", etc. Score 1.0 if all major claims are clearly backed by the trajectory. Score 0.5 if most major claims are supported but some are not visible in the trajectory. Score 0.0 if many major claims appear to be hallucinated or unsupported by anything the agent actually queried.

### BONUS rubric (1 dimension, bonus weight 0.05)

9. **cites_specific_evidence** (bonus weight 0.05): Does the answer cite 3+ specific pieces of evidence (ticket IDs, kid names, trace IDs, timestamps, Slack quotes)? 1.0 for 3+; 0.5 for 1-2; 0.0 for none.

## Output format

Return ONLY a JSON object. NO prose, NO markdown fences, NO anything outside the JSON:

{{
  "scores": {{
    "identify_chg_1891": 0.0,
    "identify_cloud2_scope": 0.0,
    "identify_state_lock_mechanism": 0.0,
    "identify_stale_key_symptom": 0.0,
    "proposes_targeted_reapply": 0.0,
    "avoids_global_rollback": 0.0,
    "explicit_elimination": 0.0,
    "evidence_supported_claims": 0.0,
    "cites_specific_evidence": 0.0
  }},
  "justifications": {{
    "identify_chg_1891": "brief sentence",
    "identify_cloud2_scope": "brief sentence",
    "identify_state_lock_mechanism": "brief sentence",
    "identify_stale_key_symptom": "brief sentence",
    "proposes_targeted_reapply": "brief sentence",
    "avoids_global_rollback": "brief sentence",
    "explicit_elimination": "brief sentence naming the alternative identified (or explaining none was)",
    "evidence_supported_claims": "brief sentence listing the main unsupported claims, if any",
    "cites_specific_evidence": "brief sentence listing what was cited"
  }}
}}
"""


def _summarize_trajectory(trajectory: list[dict], max_steps: int = 30, per_result_chars: int = 220) -> str:
    """Compact representation of the trajectory for the judge prompt.

    Each step becomes a line with the tool + short key args and a short
    excerpt of the observed result. Long results are truncated to keep the
    prompt short. `submit_answer` steps and evaluation observations are
    skipped (we're about to grade the answer separately).
    """
    if not trajectory:
        return "(empty trajectory)"

    lines: list[str] = []
    shown = 0
    for step in trajectory:
        if shown >= max_steps:
            lines.append(f"... ({len(trajectory) - shown} more steps truncated)")
            break
        action = step.get("action")
        if not action:
            continue
        tool_name = action.get("tool_name", "?")
        if tool_name == "submit_answer":
            # Don't include the final answer -- we grade it separately.
            continue
        args = action.get("arguments", {}) or {}
        obs_type = step.get("observation_type", "?")
        content_preview = (step.get("content_preview") or "").strip()
        if len(content_preview) > per_result_chars:
            content_preview = content_preview[:per_result_chars].rstrip() + "..."
        content_preview = content_preview.replace("\n", " / ")
        compact_args = ", ".join(
            f"{k}={_compact_value(v)}"
            for k, v in args.items()
            if v not in (None, "", [], {})
        )
        lines.append(f"  step {step.get('step', '?'):>2}  {tool_name}({compact_args})")
        lines.append(f"         -> [{obs_type}] {content_preview}")
        shown += 1
    return "\n".join(lines)


def _compact_value(v: Any) -> str:
    if isinstance(v, str):
        return v if len(v) < 60 else v[:60] + "..."
    return json.dumps(v, separators=(",", ":"), default=str)[:60]


class LLMJudge:
    """Sonnet-graded terminal scorer, trajectory-aware."""

    CORE_WEIGHTS: dict[str, float] = {
        "identify_chg_1891": 0.15,
        "identify_cloud2_scope": 0.15,
        "identify_state_lock_mechanism": 0.20,
        "identify_stale_key_symptom": 0.15,
        "proposes_targeted_reapply": 0.10,
        "avoids_global_rollback": 0.05,
        "explicit_elimination": 0.10,
        "evidence_supported_claims": 0.10,
    }
    BONUS_WEIGHTS: dict[str, float] = {
        "cites_specific_evidence": 0.05,
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

    def grade(
        self,
        root_cause: str,
        fix: str,
        trajectory: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """Grade one submit_answer against trajectory + ground truth.

        If `trajectory` is None or empty, the evidence-supported-claims
        dimension falls back to a text-only read.
        """
        trajectory_summary = _summarize_trajectory(trajectory or [])
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            trajectory_summary=trajectory_summary,
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
