# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
FastAPI application for the PagerBench Environment.

This module creates an HTTP server that exposes the CloudSecEnvironment
over HTTP and WebSocket endpoints, compatible with EnvClient. It also
mounts a static "incident workbench" UI at ``/`` and ``/web`` (replacing
the default OpenEnv shell) so judges can drive the env interactively.

Endpoints:
    - POST /reset: Reset the environment
    - POST /step: Execute an action
    - GET /state: Get current environment state
    - GET /schema: Get action/observation schemas
    - WS /ws: WebSocket endpoint for persistent sessions
    - GET /: PagerBench incident workbench (custom UI)
    - GET /ui/config: Tool list + task metadata for the workbench

Usage:
    # Development (with auto-reload):
    uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

    # Production:
    uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 4
"""

from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with '\n    uv sync\n'"
    ) from e

try:
    from ..models import CloudSecAction, CloudSecObservation
    from .cloud_sec_env_environment import CloudSecEnvironment
except (ImportError, ValueError):
    # Relative imports fail when this module is loaded as the top-level
    # package (e.g. uvicorn server.app:app from /app/env on HF Spaces).
    # Fall back to absolute imports.
    from models import CloudSecAction, CloudSecObservation
    from server.cloud_sec_env_environment import CloudSecEnvironment


_STATIC_DIR = Path(__file__).resolve().parent / "static"


# Tool schemas for the workbench UI. Mirrors `cloud_sec_env/agent/tool_specs.py`
# but kept self-contained so the env package doesn't depend on the agent package.
_CLOUDS = ["cloud-1", "cloud-2", "cloud-3"]
_SERVICES = [
    "api-gateway",
    "auth-svc",
    "sts-broker",
    "policy-svc",
    "audit-logger",
    "ml-scorer",
]
_CHANNELS = ["#sre-oncall", "#infra-terraform", "#acme-support", "#deploys", "#general"]
_TICKET_TYPES = ["CHG", "INC"]

_UI_TOOLS: list[dict[str, Any]] = [
    {
        "name": "logs_search",
        "description": (
            "Search log lines emitted by services across all clouds. "
            "Scope with cloud + service to reduce noise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cloud": {"type": "string", "enum": _CLOUDS, "description": "Restrict to one cloud."},
                "service": {"type": "string", "enum": _SERVICES, "description": "Restrict to one service."},
                "query": {"type": "string", "description": "Free-text search, e.g. 'JWT signature'."},
                "time_range": {
                    "type": "string",
                    "description": "Default 'T-60m..T+0'. Use T-{N}m..T+0 or absolute ISO range.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows. Default 20.",
                },
            },
        },
    },
    {
        "name": "trace_get",
        "description": (
            "Retrieve the full span tree for a trace_id. Use after logs_search "
            "surfaces a trace_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "description": "Trace ID from a log line."},
            },
            "required": ["trace_id"],
        },
    },
    {
        "name": "metric_query",
        "description": (
            "Query a named time-series metric "
            "(e.g. 'sts.jwt_validation_failures', 'auth_svc.http.5xx_rate')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_name": {"type": "string", "description": "Dotted metric name."},
                "cloud": {"type": "string", "enum": _CLOUDS},
                "service": {"type": "string", "enum": _SERVICES},
                "time_range": {"type": "string", "description": "Default 'T-60m..T+0'."},
                "step": {"type": "string", "description": "Aggregation step, e.g. '1m', '5m'."},
            },
            "required": ["metric_name"],
        },
    },
    {
        "name": "ticket_search",
        "description": (
            "Search the ticketing system. CHG = change tickets, INC = incident tickets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search."},
                "ticket_type": {"type": "string", "enum": _TICKET_TYPES},
                "time_range": {"type": "string", "description": "Default 'T-7d..T+0'."},
                "limit": {"type": "integer", "description": "Default 10."},
            },
        },
    },
    {
        "name": "slack_search",
        "description": (
            "Search team chat messages across SRE / infra / deploys / general channels."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": _CHANNELS},
                "query": {"type": "string", "description": "Free-text search."},
                "time_range": {"type": "string", "description": "Default 'T-7d..T+0'."},
                "limit": {"type": "integer", "description": "Default 10."},
            },
        },
    },
    {
        "name": "kb_search",
        "description": (
            "Search the internal knowledge base (runbooks, architecture docs). "
            "Some docs may be stale — check 'last edited'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search."},
                "limit": {"type": "integer", "description": "Default 3."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "submit_answer",
        "description": (
            "Submit your final answer. ENDS THE EPISODE. Provide a clear root_cause "
            "and a concrete fix. Reward is graded against the trajectory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "root_cause": {
                    "type": "string",
                    "description": "Paragraph: what caused the incident, what failed, scope.",
                    "maxLength": 5000,
                },
                "fix": {
                    "type": "string",
                    "description": "Paragraph: the specific remediation. Avoid global rollbacks.",
                    "maxLength": 5000,
                },
            },
            "required": ["root_cause", "fix"],
        },
    },
]

_UI_TASKS: list[dict[str, Any]] = [
    {
        "task_name": "task_01_oidc_rotation",
        "label": "OIDC key rotation — auth_svc 5xx spike on cloud-2",
        "preview": (
            "Click \"Reset Episode\" to fetch the live alert and start the 30-step "
            "investigation. The agent has 6 tools across logs / traces / metrics / "
            "tickets / Slack / KB."
        ),
    },
]


# Create the app with web interface and README integration
app = create_app(
    CloudSecEnvironment,
    CloudSecAction,
    CloudSecObservation,
    env_name="cloud_sec_env",
    max_concurrent_envs=1,  # increase this number to allow more concurrent WebSocket sessions
)


# ---------------------------------------------------------------------------
# Custom workbench UI (replaces OpenEnv's default /web shell)
# ---------------------------------------------------------------------------

if _STATIC_DIR.exists():
    # Drop OpenEnv's optional default web shell at "/" and "/web" so our
    # custom incident workbench is the visible Space UI. The API/MCP routes
    # registered by create_app are preserved.
    app.router.routes = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) not in {"/", "/web"}
    ]
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/web", include_in_schema=False)
    @app.get("/web/", include_in_schema=False)
    def _web_index() -> FileResponse:
        """Serve the PagerBench incident workbench."""
        return FileResponse(_STATIC_DIR / "index.html")


@app.get("/ui/config", include_in_schema=False)
def _ui_config() -> dict[str, Any]:
    """Return UI metadata used by the workbench frontend."""
    return {
        "default_task": "task_01_oidc_rotation",
        "max_steps": 30,
        "tasks": _UI_TASKS,
        "tools": _UI_TOOLS,
        "clouds": _CLOUDS,
        "services": _SERVICES,
        "channels": _CHANNELS,
        "ticket_types": _TICKET_TYPES,
    }


def main(host: str = "0.0.0.0", port: int = 8000):
    """Entry point for direct execution via uv run or python -m."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    main(port=args.port)
