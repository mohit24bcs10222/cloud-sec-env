# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Tool specifications for Anthropic's tool-use API.

Each entry corresponds to one of our 6 tools (plus submit_answer) and is
translated from SCHEMAS.md into the input_schema JSON-Schema format that
Anthropic expects.
"""

from __future__ import annotations


CLOUDS = ["cloud-1", "cloud-2", "cloud-3"]
SERVICES = ["api-gateway", "auth-svc", "sts-broker", "policy-svc", "audit-logger", "ml-scorer"]
CHANNELS = ["#sre-oncall", "#infra-terraform", "#acme-support", "#deploys", "#general"]
TICKET_TYPES = ["CHG", "INC"]


ANTHROPIC_TOOLS: list[dict] = [
    # ---------- 1. logs_search ----------
    {
        "name": "logs_search",
        "description": (
            "Search log lines emitted by services across all clouds. Use this to find error messages, "
            "trace IDs, and correlate events over time. Scope with `cloud` and `service` to reduce noise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cloud": {"type": "string", "enum": CLOUDS, "description": "Restrict to one cloud."},
                "service": {"type": "string", "enum": SERVICES, "description": "Restrict to one service."},
                "query": {"type": "string", "description": "Free-text substring search against log message."},
                "time_range": {
                    "type": "string",
                    "description": "Relative (e.g. 'T-60m..T+0') or absolute ISO (e.g. '2026-04-22T13:00Z..2026-04-22T14:00Z'). Default 'T-60m..T+0'.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Max rows returned. Default 20."},
            },
            "required": [],
        },
    },

    # ---------- 2. trace_get ----------
    {
        "name": "trace_get",
        "description": (
            "Retrieve the full span tree (cross-service request path) for a given trace_id. "
            "Use this after logs_search finds a trace_id of interest, to see where and how a request failed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "description": "Trace ID (usually surfaced by logs_search)."},
            },
            "required": ["trace_id"],
        },
    },

    # ---------- 3. metric_query ----------
    {
        "name": "metric_query",
        "description": (
            "Query a named time-series metric (e.g. 'sts.jwt_validation_failures', "
            "'auth_svc.http.5xx_rate', 'ml_scorer.cpu_throttle_pct'). Good for spotting step changes "
            "and comparing across clouds."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_name": {"type": "string", "description": "Dotted metric name."},
                "cloud": {"type": "string", "enum": CLOUDS},
                "service": {"type": "string", "enum": SERVICES},
                "time_range": {"type": "string", "description": "Default 'T-60m..T+0'."},
                "step": {"type": "string", "description": "Aggregation step, e.g. '1m', '5m', '15m'. Default '1m'."},
            },
            "required": ["metric_name"],
        },
    },

    # ---------- 4. ticket_search ----------
    {
        "name": "ticket_search",
        "description": (
            "Search the ticketing system. Change tickets (type CHG) are key for finding recent config/deploy "
            "changes that may have caused the incident. Incident tickets (INC) show related alerts and reports."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text substring search."},
                "ticket_type": {"type": "string", "enum": TICKET_TYPES},
                "time_range": {"type": "string", "description": "Default 'T-7d..T+0'."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Default 10."},
            },
            "required": [],
        },
    },

    # ---------- 5. slack_search ----------
    {
        "name": "slack_search",
        "description": (
            "Search team chat messages. Useful for finding engineer-to-engineer coordination "
            "(e.g., someone flagging a deploy conflict). Channels: #sre-oncall, #infra-terraform, "
            "#deploys, #acme-support, #general."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": CHANNELS},
                "query": {"type": "string", "description": "Free-text substring search."},
                "time_range": {"type": "string", "description": "Default 'T-7d..T+0'."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Default 10."},
            },
            "required": [],
        },
    },

    # ---------- 6. kb_search ----------
    {
        "name": "kb_search",
        "description": (
            "Search the internal knowledge base (runbooks, architecture docs, retrospectives). "
            "Returns top matches with full markdown content. Some docs may be stale -- check `last edited` date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search across title and body."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Default 3."},
            },
            "required": ["query"],
        },
    },

    # ---------- 7. submit_answer (terminal) ----------
    {
        "name": "submit_answer",
        "description": (
            "Submit your final answer. This ends the investigation. Provide a clear root_cause "
            "and a concrete fix. Do not call this until you are confident."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "root_cause": {
                    "type": "string",
                    "description": "Paragraph describing what caused the incident. Name the originating change, the failure mode, and the scope.",
                },
                "fix": {
                    "type": "string",
                    "description": "Paragraph describing the remediation. Be specific; avoid global rollbacks if only one cloud is affected.",
                },
            },
            "required": ["root_cause", "fix"],
        },
    },
]


SYSTEM_PROMPT = """You are an on-call Site Reliability Engineer (SRE) at NimbusGuard, a cloud-security SaaS.

You've been paged with an incident alert. Investigate using the tools available, identify the root cause, and propose a fix.

**Environment:** 3 cloud deployments (cloud-1 us-east, cloud-2 us-west, cloud-3 eu-west). Core services per cloud: api-gateway, auth-svc, sts-broker, policy-svc, audit-logger. Customers federate identity via OIDC.

**Budget:** 30 tool calls maximum.

**When you submit_answer, provide:**
- root_cause: what actually broke and why. A senior SRE proves their conclusion against alternatives, so identify the most plausible alternative hypothesis your investigation surfaced and explain why it isn't the cause.
- fix: the specific remediation.
"""
