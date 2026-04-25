# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Tool implementations for the Cloud Sec Env environment.

Each tool:
  - validates its arguments
  - filters the relevant data slice via the DataStore
  - formats a human-readable `content` string for the agent
  - returns a structured `data` dict for the reward scorer / trajectory log

Tools raise ToolError on invalid args. The environment catches and
converts to an `error` observation (not an episode terminator).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .data_loader import DataStore


# ----------------------------------------------------------------------
# Enums (kept in sync with SCHEMAS.md)
# ----------------------------------------------------------------------

VALID_CLOUDS = {"cloud-1", "cloud-2", "cloud-3"}
VALID_SERVICES = {
    "api-gateway", "auth-svc", "sts-broker", "policy-svc", "audit-logger",
    "ml-scorer",  # present in fixtures as ancillary service
}
VALID_CHANNELS = {"#sre-oncall", "#infra-terraform", "#acme-support", "#deploys", "#general"}
VALID_TICKET_TYPES = {"CHG", "INC"}


class ToolError(Exception):
    """Raised when tool args are invalid. Environment surfaces to the agent as an error observation."""


# ----------------------------------------------------------------------
# Text search helpers
# ----------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    """Lowercase and strip punctuation that shouldn't affect search
    (hyphens, underscores). 'state-lock' and 'state lock' both -> 'state lock'."""
    return re.sub(r"[-_/]", " ", text.lower())


def _query_words(query: str) -> list[str]:
    return _WORD_RE.findall(_normalize(query))


def _matches_query(haystack: str, query: str | None) -> bool:
    """True if every whitespace-separated word in query appears in haystack."""
    if not query:
        return True
    hay = _normalize(haystack)
    return all(word in hay for word in _query_words(query))


def _query_score(haystack: str, query: str | None) -> int:
    """Number of query-word occurrences in haystack. Used for ranking."""
    if not query:
        return 0
    hay = _normalize(haystack)
    return sum(hay.count(word) for word in _query_words(query))


# ----------------------------------------------------------------------
# Time-range parsing
# ----------------------------------------------------------------------

_REL_RE = re.compile(r"^T([+-])(\d+)([smhd])$")


def _parse_relative(expr: str, alert_time: datetime) -> datetime:
    """Parse 'T-60m', 'T+0', 'T+30s', etc."""
    expr = expr.strip()
    if expr == "T+0" or expr == "T-0" or expr == "T":
        return alert_time
    m = _REL_RE.match(expr)
    if not m:
        raise ToolError(f"Invalid time expression '{expr}'. Expected like 'T-60m' or 'T+0'.")
    sign, n, unit = m.groups()
    n = int(n)
    unit_seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    delta = timedelta(seconds=n * unit_seconds)
    return alert_time - delta if sign == "-" else alert_time + delta


def _parse_absolute(expr: str) -> datetime:
    try:
        return datetime.fromisoformat(expr.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ToolError(f"Invalid timestamp '{expr}'. Expected ISO-8601 like '2026-04-22T13:00Z'.")


def parse_time_range(time_range: str, alert_time: datetime) -> tuple[datetime, datetime]:
    """Parse a time_range string like 'T-60m..T+0' or absolute ISO ranges."""
    if ".." not in time_range:
        raise ToolError(f"time_range must contain '..' (e.g. 'T-60m..T+0'). Got: '{time_range}'.")
    start_expr, end_expr = time_range.split("..", 1)
    is_relative = start_expr.strip().startswith("T") or end_expr.strip().startswith("T")
    if is_relative:
        start = _parse_relative(start_expr, alert_time)
        end = _parse_relative(end_expr, alert_time)
    else:
        start = _parse_absolute(start_expr)
        end = _parse_absolute(end_expr)
    if start > end:
        raise ToolError(f"time_range start ({start_expr}) is after end ({end_expr}).")
    return start, end


# ----------------------------------------------------------------------
# Shared validators
# ----------------------------------------------------------------------

def _validate_cloud(value: Any) -> str | None:
    if value is None:
        return None
    if value not in VALID_CLOUDS:
        raise ToolError(f"Unknown cloud '{value}'. Valid: {sorted(VALID_CLOUDS)}.")
    return value


def _validate_service(value: Any) -> str | None:
    if value is None:
        return None
    if value not in VALID_SERVICES:
        raise ToolError(f"Unknown service '{value}'. Valid: {sorted(VALID_SERVICES)}.")
    return value


def _validate_channel(value: Any) -> str | None:
    if value is None:
        return None
    if value not in VALID_CHANNELS:
        raise ToolError(f"Unknown channel '{value}'. Valid: {sorted(VALID_CHANNELS)}.")
    return value


def _validate_ticket_type(value: Any) -> str | None:
    if value is None:
        return None
    if value not in VALID_TICKET_TYPES:
        raise ToolError(f"Unknown ticket_type '{value}'. Valid: {sorted(VALID_TICKET_TYPES)}.")
    return value


def _validate_limit(value: Any, default: int, hard_cap: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value < 1:
        raise ToolError(f"limit must be a positive integer. Got: {value!r}.")
    return min(value, hard_cap)


# ----------------------------------------------------------------------
# 1. logs_search
# ----------------------------------------------------------------------

def _fmt_log_row(r: dict[str, Any]) -> str:
    """Render one log row as a single line."""
    ts = r["timestamp"]
    cloud = r.get("cloud", "?")
    service = r.get("service", "?")
    level = r.get("level", "INFO")
    trace_id = r.get("trace_id")
    req_id = r.get("request_id")
    trace_part = f"trace={trace_id}" if trace_id else "(no trace)"
    req_part = f"req={req_id}" if req_id else ""
    trailer = " ".join(p for p in [req_part, trace_part] if p).strip()
    return f"[{ts}] {cloud} {service:<14} {level:<5} {trailer} | {r.get('message', '')}"


def logs_search(args: dict[str, Any], store: DataStore) -> tuple[str, dict[str, Any]]:
    cloud = _validate_cloud(args.get("cloud"))
    service = _validate_service(args.get("service"))
    query = args.get("query") or None
    time_range = args.get("time_range", "T-60m..T+0")
    limit = _validate_limit(args.get("limit"), default=20, hard_cap=100)

    start, end = parse_time_range(time_range, store.alert_time)

    matched = []
    for row in store.logs:
        ts = store.parse_log_ts(row)
        if ts < start or ts > end:
            continue
        if cloud and row.get("cloud") != cloud:
            continue
        if service and row.get("service") != service:
            continue
        if not _matches_query(row.get("message", ""), query):
            continue
        matched.append(row)

    total = len(matched)
    returned_rows = matched[:limit]

    lines = [
        f"logs_search(cloud={cloud}, service={service}, time_range={time_range}, query={query!r}, limit={limit}):",
        f"{total} matching log lines; showing first {len(returned_rows)}.",
        "",
    ]
    for r in returned_rows:
        lines.append(_fmt_log_row(r))
    if total > len(returned_rows):
        lines.append("")
        lines.append(f"(truncated; {total} total, {len(returned_rows)} shown -- raise `limit` to see more)")

    content = "\n".join(lines)
    data = {
        "query_params": {"cloud": cloud, "service": service, "query": query, "time_range": time_range, "limit": limit},
        "total_matches": total,
        "returned": len(returned_rows),
        "rows": returned_rows,
    }
    return content, data


# ----------------------------------------------------------------------
# 2. trace_get
# ----------------------------------------------------------------------

def _fmt_trace_tree(trace: dict[str, Any]) -> list[str]:
    """Render spans as an indented tree."""
    spans = trace.get("spans", [])
    # Index by span_id for parent lookup.
    by_id = {s["span_id"]: s for s in spans}
    children: dict[str | None, list[dict[str, Any]]] = {}
    for s in spans:
        children.setdefault(s.get("parent_id"), []).append(s)

    lines = []

    def fmt_span(span: dict[str, Any], prefix: str, is_last: bool) -> None:
        duration = span.get("duration_ms", "?")
        status = span.get("status", "?")
        op = f"{span.get('service', '?')} {span.get('operation', '?')}"
        start = span.get("start", "?")
        attrs = span.get("attributes", {})
        err = attrs.get("error")
        http = attrs.get("http.status_code")
        badge_parts = [status]
        if http:
            badge_parts.append(str(http))
        if err:
            badge_parts.append(err)
        badge = " ".join(badge_parts)
        lines.append(f"{prefix}{op:<42} [{start}, {duration}ms, {badge}]")

    # Render from roots (parent_id is None).
    roots = children.get(None, [])
    def walk(span: dict[str, Any], prefix: str, child_prefix: str) -> None:
        fmt_span(span, prefix, False)
        kids = children.get(span["span_id"], [])
        for i, kid in enumerate(kids):
            is_last = i == len(kids) - 1
            branch = "└─ " if is_last else "├─ "
            next_child_prefix = child_prefix + ("   " if is_last else "│  ")
            walk(kid, child_prefix + branch, next_child_prefix)

    for i, root in enumerate(roots):
        walk(root, "", "")

    return lines


def trace_get(args: dict[str, Any], store: DataStore) -> tuple[str, dict[str, Any]]:
    trace_id = args.get("trace_id")
    if isinstance(trace_id, list) and len(trace_id) == 1 and isinstance(trace_id[0], str):
        # Tolerate single-element-list quirks that some prompted-JSON LLMs produce.
        trace_id = trace_id[0]
    if not trace_id or not isinstance(trace_id, str):
        raise ToolError("trace_get requires arg 'trace_id' as a string (got: %r)." % (trace_id,))
    trace = store.traces.get(trace_id)
    if not trace:
        raise ToolError(f"Unknown trace_id '{trace_id}'. No such trace in our store.")

    num_spans = len(trace.get("spans", []))
    header = (
        f"trace_get(trace_id={trace_id}):\n"
        f"Trace {trace_id} -- {num_spans} spans, total duration {trace.get('total_duration_ms', '?')}ms, "
        f"status={trace.get('status', '?')}"
    )
    tree = _fmt_trace_tree(trace)
    lines = [header, ""] + tree
    if trace.get("partial"):
        lines.append("")
        lines.append(f"({trace.get('partial_note', 'partial trace -- some spans missing')})")

    content = "\n".join(lines)
    data = dict(trace)  # shallow copy so we don't mutate
    return content, data


# ----------------------------------------------------------------------
# 3. metric_query
# ----------------------------------------------------------------------

def metric_query(args: dict[str, Any], store: DataStore) -> tuple[str, dict[str, Any]]:
    metric_name = args.get("metric_name")
    if not metric_name or not isinstance(metric_name, str):
        available = sorted({r["metric"] for r in store.metrics})
        raise ToolError(f"metric_query requires arg 'metric_name'. Available: {available}.")

    cloud = _validate_cloud(args.get("cloud"))
    service = _validate_service(args.get("service"))
    time_range = args.get("time_range", "T-60m..T+0")
    start, end = parse_time_range(time_range, store.alert_time)

    # step is accepted for API consistency but our fixture stores pre-aggregated samples,
    # so we just filter and echo step in the response.
    step = args.get("step", "1m")

    samples = []
    for row in store.metrics:
        if row["metric"] != metric_name:
            continue
        if cloud and row.get("cloud") != cloud:
            continue
        if service and row.get("service") != service:
            continue
        ts = store.parse_metric_ts(row)
        if ts < start or ts > end:
            continue
        samples.append(row)

    if not samples:
        content = (
            f"metric_query(metric={metric_name}, cloud={cloud}, service={service}, time_range={time_range}, step={step}):\n"
            "No samples in the requested time range."
        )
        data = {
            "query_params": {"metric_name": metric_name, "cloud": cloud, "service": service, "time_range": time_range, "step": step},
            "metric_name": metric_name,
            "samples": [],
            "summary": {"count": 0},
        }
        return content, data

    samples.sort(key=store.parse_metric_ts)
    values = [s["v"] for s in samples]
    summary = {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": round(sum(values) / len(values), 3),
        "last": values[-1],
    }

    # Pick ~24 evenly-spaced display samples.
    display_count = min(len(samples), 24)
    if display_count <= 1:
        step_idx = 1
    else:
        step_idx = max(1, len(samples) // display_count)
    display = samples[::step_idx]
    if display[-1] is not samples[-1]:
        display.append(samples[-1])

    lines = [
        f"metric_query(metric={metric_name}, cloud={cloud}, service={service}, time_range={time_range}, step={step}):",
        f"{summary['count']} samples; min={summary['min']}, max={summary['max']}, mean={summary['mean']}, last={summary['last']}.",
        "",
        f"Showing {len(display)} samples:",
    ]
    for s in display:
        lines.append(f"  {s['t']}   {s['v']}")

    content = "\n".join(lines)
    data = {
        "query_params": {"metric_name": metric_name, "cloud": cloud, "service": service, "time_range": time_range, "step": step},
        "metric_name": metric_name,
        "samples": samples,
        "summary": summary,
    }
    return content, data


# ----------------------------------------------------------------------
# 4. ticket_search
# ----------------------------------------------------------------------

def ticket_search(args: dict[str, Any], store: DataStore) -> tuple[str, dict[str, Any]]:
    query = args.get("query") or None
    ticket_type = _validate_ticket_type(args.get("ticket_type"))
    time_range = args.get("time_range", "T-7d..T+0")
    limit = _validate_limit(args.get("limit"), default=10, hard_cap=50)

    start, end = parse_time_range(time_range, store.alert_time)

    matched = []
    for t in store.tickets:
        ts = store.parse_ticket_ts(t)
        if ts < start or ts > end:
            continue
        if ticket_type and t.get("type") != ticket_type:
            continue
        haystack = f"{t.get('title', '')}\n{t.get('body', '')}"
        if not _matches_query(haystack, query):
            continue
        matched.append(t)

    matched.sort(key=store.parse_ticket_ts, reverse=True)
    returned = matched[:limit]

    lines = [
        f"ticket_search(query={query!r}, ticket_type={ticket_type}, time_range={time_range}, limit={limit}):",
        f"Found {len(matched)} matches; showing first {len(returned)}.",
        "",
    ]
    for t in returned:
        lines.append(
            f"{t['id']}  {t['title']}  (author: {t.get('author', '?')})  {t.get('created', '?')}  {t.get('status', '?')}"
        )
        # Wrap body to ~80 chars for readability, indented.
        body = (t.get("body") or "").strip()
        if body:
            for bl in body.split("\n"):
                lines.append(f"  {bl}")
        lines.append("")

    content = "\n".join(lines).rstrip()
    data = {
        "query_params": {"query": query, "ticket_type": ticket_type, "time_range": time_range, "limit": limit},
        "total_matches": len(matched),
        "returned": len(returned),
        "tickets": returned,
    }
    return content, data


# ----------------------------------------------------------------------
# 5. slack_search
# ----------------------------------------------------------------------

def slack_search(args: dict[str, Any], store: DataStore) -> tuple[str, dict[str, Any]]:
    channel = _validate_channel(args.get("channel"))
    query = args.get("query") or None
    time_range = args.get("time_range", "T-7d..T+0")
    limit = _validate_limit(args.get("limit"), default=10, hard_cap=50)

    start, end = parse_time_range(time_range, store.alert_time)

    matched = []
    for m in store.slack:
        ts = store.parse_slack_ts(m)
        if ts < start or ts > end:
            continue
        if channel and m.get("channel") != channel:
            continue
        if not _matches_query(m.get("text", ""), query):
            continue
        matched.append(m)

    matched.sort(key=store.parse_slack_ts)
    returned = matched[:limit]

    lines = [
        f"slack_search(channel={channel}, query={query!r}, time_range={time_range}, limit={limit}):",
        f"Found {len(matched)} matches; showing first {len(returned)}.",
        "",
    ]
    for m in returned:
        thread_marker = "  (in thread)" if m.get("thread_ts") else ""
        lines.append(f"[{m['channel']}] {m['timestamp']}  @{m.get('author', '?')}{thread_marker}")
        lines.append(f"  {m.get('text', '')}")
        lines.append("")

    content = "\n".join(lines).rstrip()
    data = {
        "query_params": {"channel": channel, "query": query, "time_range": time_range, "limit": limit},
        "total_matches": len(matched),
        "returned": len(returned),
        "messages": returned,
    }
    return content, data


# ----------------------------------------------------------------------
# 6. kb_search
# ----------------------------------------------------------------------

def kb_search(args: dict[str, Any], store: DataStore) -> tuple[str, dict[str, Any]]:
    query = args.get("query")
    if not query or not isinstance(query, str) or not query.strip():
        raise ToolError("kb_search requires a non-empty 'query' string.")
    limit = _validate_limit(args.get("limit"), default=3, hard_cap=5)

    matched = [d for d in store.kb_docs if _matches_query(d["full_text"], query)]

    # Rank by: all query words in title (strongest), then body-term frequency.
    def score(d: dict[str, Any]) -> tuple[int, int]:
        title_hit = 1 if _matches_query(d.get("title") or "", query) else 0
        body_hits = _query_score(d["full_text"], query)
        return (title_hit, body_hits)
    matched.sort(key=score, reverse=True)
    returned = matched[:limit]

    lines = [
        f"kb_search(query={query!r}, limit={limit}):",
        f"Found {len(matched)} matches. Showing top {len(returned)} with full content.",
        "",
    ]
    for d in returned:
        last_edited = d.get("last_edited")
        last_edited_str = last_edited.date().isoformat() if last_edited else "unknown"
        lines.append("=" * 60)
        lines.append(f"[{d.get('path', '?')}] ({d.get('id', '?')})  |  last edited {last_edited_str}")
        lines.append("=" * 60)
        lines.append(d.get("body_md", "").rstrip())
        lines.append("")

    content = "\n".join(lines).rstrip()
    # Strip full_text from data output (it's a search-index helper, not useful to consumers).
    data_docs = [
        {k: v for k, v in d.items() if k != "full_text"} | {"last_edited": (d["last_edited"].isoformat() if d.get("last_edited") else None)}
        for d in returned
    ]
    data = {
        "query_params": {"query": query, "limit": limit},
        "total_matches": len(matched),
        "returned": len(returned),
        "docs": data_docs,
    }
    return content, data


# ----------------------------------------------------------------------
# Registry -- environment dispatches here.
# ----------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Callable[[dict[str, Any], DataStore], tuple[str, dict[str, Any]]]] = {
    "logs_search": logs_search,
    "trace_get": trace_get,
    "metric_query": metric_query,
    "ticket_search": ticket_search,
    "slack_search": slack_search,
    "kb_search": kb_search,
}


def call_tool(tool_name: str, args: dict[str, Any], store: DataStore) -> tuple[str, dict[str, Any]]:
    """Dispatch to a tool by name. Raises ToolError for unknown tools or bad args."""
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        valid = sorted(list(TOOL_REGISTRY.keys()) + ["submit_answer"])
        raise ToolError(f"Unknown tool_name '{tool_name}'. Valid: {valid}.")
    return fn(args, store)
