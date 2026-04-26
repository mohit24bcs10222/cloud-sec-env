# PagerBench — Locked Schemas

> Single source of truth for Action / Observation / tool signatures. Person A (env) and Person B (training/agent) both code against this doc. Changes require a conversation.

## Action (what the agent emits)

```
CloudSecAction {
  tool_name:  str                   # one of 6 tools, or "submit_answer"
  arguments:  dict[str, Any]        # per-tool args, validated server-side
  reasoning:  str | None            # optional CoT, logged not scored
}
```

## Observation (what the env returns)

```
CloudSecObservation {
  content:           str             # human-readable text the agent reads
  data:              dict[str, Any]  # structured mirror for scoring/logging
  observation_type:  "alert" | "tool_result" | "error" | "evaluation"
  steps_remaining:   int

  # inherited from base Observation
  done:              bool
  reward:            float | None
  metadata:          dict[str, Any]
}
```

Max steps per episode: **30**. Exceeding this without a `submit_answer` → forced termination with `reward=0`.

---

## Valid values (referenced by tool signatures below)

| Enum | Values |
|---|---|
| `CLOUD` | `cloud-1`, `cloud-2`, `cloud-3` |
| `SERVICE` | `api-gateway`, `auth-svc`, `sts-broker`, `policy-svc`, `audit-logger` |
| `CHANNEL` | `#sre-oncall`, `#infra-terraform`, `#acme-support`, `#deploys`, `#general` |
| `TICKET_TYPE` | `CHG` (change), `INC` (incident) |

Invalid values → `observation_type: "error"`, no episode termination, agent can retry.

Time ranges accept two formats:
- Relative: `"T-60m..T+0"`, `"T-24h..T+0"`, etc. (`T` = alert trigger time)
- Absolute: `"2026-04-22T13:00Z..2026-04-22T14:30Z"`

---

## 1. `logs_search`

Search the log store for matching entries.

### Arguments

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `cloud` | `CLOUD \| None` | no | — | Scope to one cloud. |
| `service` | `SERVICE \| None` | no | — | Scope to one service. |
| `query` | `str` | no | — | Free-text substring match against log message. |
| `time_range` | `str` | no | `"T-60m..T+0"` | Time window. |
| `limit` | `int` | no | `20` | Max rows returned (server-capped at 100). |

### `content` format

```
logs_search(cloud=cloud-2, service=auth-svc, time_range=T-60m..T+0, query="signature"):
47 matching log lines; showing first 20.

[2026-04-22 14:02:17.341] cloud-2 sts-broker ERROR req=a1b2c3 trace=a1b2c3 | JWT signature verification failed: kid=rsa-2025-q4 unknown
[2026-04-22 14:02:17.412] cloud-2 sts-broker ERROR req=a1b2c4 trace=a1b2c4 | JWT signature verification failed: kid=rsa-2025-q4 unknown
[2026-04-22 14:02:17.683] cloud-2 sts-broker ERROR (no trace) | JWT signature verification failed: kid=rsa-2025-q4 unknown
...
(truncated; 47 total, 20 shown -- raise `limit` to see more)
```

### `data` format

```json
{
  "query_params": { ... echo of inputs ... },
  "total_matches": 47,
  "returned": 20,
  "rows": [
    {
      "timestamp": "2026-04-22T14:02:17.341Z",
      "cloud": "cloud-2",
      "service": "sts-broker",
      "level": "ERROR",
      "message": "JWT signature verification failed: kid=rsa-2025-q4 unknown",
      "trace_id": "a1b2c3",
      "request_id": "req-001"
    },
    ...
  ]
}
```

### Edge cases

- Unknown `cloud` or `service` → error observation with the valid enum values listed.
- Zero matches → valid result with `total_matches=0`, empty rows. Not an error.
- Intentionally: some rows have `trace_id=null` (realistic coherence gaps).

---

## 2. `trace_get`

Retrieve the full span tree of a request by trace_id.

### Arguments

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `trace_id` | `str` | **yes** | — | The trace ID to fetch. |

### `content` format

```
trace_get(trace_id=a1b2c3):
Trace a1b2c3 -- 5 spans, total duration 214ms, status=ERROR

api-gateway /v1/login              [14:02:17.280 -> 14:02:17.494, 214ms, ERROR 401]
└─ auth-svc /sts/validate          [14:02:17.285 -> 14:02:17.491, 206ms, ERROR 401]
   └─ sts-broker jwt.verify        [14:02:17.340 -> 14:02:17.343,   3ms, ERROR signature_failed]
      ├─ sts-broker cache.lookup   [14:02:17.340 -> 14:02:17.341,   1ms, OK]
      └─ sts-broker crypto.verify  [14:02:17.341 -> 14:02:17.343,   2ms, ERROR kid_mismatch]
```

If partial: append `(3 of 5 expected spans present -- 2 missing)`.

### `data` format

```json
{
  "trace_id": "a1b2c3",
  "total_duration_ms": 214,
  "status": "ERROR",
  "spans": [
    {
      "span_id": "s1",
      "parent_id": null,
      "service": "api-gateway",
      "operation": "/v1/login",
      "start": "2026-04-22T14:02:17.280Z",
      "duration_ms": 214,
      "status": "ERROR",
      "attributes": {"http.status_code": 401}
    },
    ...
  ]
}
```

### Edge cases

- Unknown trace_id → error observation.
- Partial trace → return what we have, note the gap in `content`.

---

## 3. `metric_query`

Query a time-series metric.

### Arguments

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `metric_name` | `str` | **yes** | — | Dotted name, e.g. `sts.jwt_validation_failures`, `auth_svc.http.5xx_rate`. |
| `cloud` | `CLOUD \| None` | no | — | Label filter. |
| `service` | `SERVICE \| None` | no | — | Label filter (ignored if metric has no `service` label). |
| `time_range` | `str` | no | `"T-60m..T+0"` | Time window. |
| `step` | `str` | no | `"1m"` | Aggregation interval, e.g. `"1m"`, `"5m"`, `"15m"`. |

### `content` format

```
metric_query(metric=sts.jwt_validation_failures, cloud=cloud-2, time_range=T-24h..T+0, step=1m):
1440 samples; min=0, max=903, mean=247, last=903.

Showing 24 evenly-spaced samples:
2026-04-21 14:00  0
2026-04-21 16:00  0
...
2026-04-22 10:00  0
2026-04-22 12:00  0
2026-04-22 13:00  87
2026-04-22 13:30  156
2026-04-22 14:00  903
```

Server does NOT auto-detect step changes — agent must recognise patterns (this is the skill we're testing).

### `data` format

```json
{
  "query_params": { ... },
  "metric_name": "sts.jwt_validation_failures",
  "labels": {"cloud": "cloud-2"},
  "samples": [
    {"t": "2026-04-21T14:00:00Z", "v": 0},
    ...
  ],
  "summary": {"min": 0, "max": 903, "mean": 247.3, "last": 903, "count": 1440}
}
```

### Edge cases

- Unknown `metric_name` → error, list the available metrics.
- No samples in the range → empty samples array, summary reports `count=0`.

---

## 4. `ticket_search`

Search the ticketing system for change and incident tickets.

### Arguments

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | `str` | no | — | Free-text substring across title + body. |
| `ticket_type` | `TICKET_TYPE \| None` | no | — | Filter to changes or incidents. |
| `time_range` | `str` | no | `"T-7d..T+0"` | Time window on ticket creation. |
| `limit` | `int` | no | `10` | Max tickets returned (server-capped at 50). |

### `content` format

```
ticket_search(query="OIDC key rotation", ticket_type=CHG, time_range=T-7d..T+0):
Found 2 matches.

CHG-1891  OIDC signing key rotation  (author: j.patel)  2026-04-22 00:15Z  closed
  Quarterly rotation of OIDC signing key across all clouds. Terraform applied cleanly --
  all 3 regions reporting success.

CHG-1872  OIDC Okta integration upgrade  (author: m.chen)  2026-04-18 09:22Z  closed
  Upgrade Okta tenant metadata file and refresh cached JWKs in sts-broker.
```

### `data` format

```json
{
  "query_params": { ... },
  "total_matches": 2,
  "returned": 2,
  "tickets": [
    {
      "id": "CHG-1891",
      "type": "CHG",
      "title": "OIDC signing key rotation",
      "author": "j.patel",
      "created": "2026-04-22T00:15Z",
      "status": "closed",
      "body": "... full body ...",
      "affected_services": ["sts-broker"],
      "affected_clouds": ["cloud-1", "cloud-2", "cloud-3"]
    },
    ...
  ]
}
```

### Edge cases

- No `query` and no filters → return most recent `limit` tickets.
- Zero matches → empty list, not an error.

---

## 5. `slack_search`

Search team chat messages.

### Arguments

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `channel` | `CHANNEL \| None` | no | — | Restrict to one channel. |
| `query` | `str` | no | — | Free-text substring. |
| `time_range` | `str` | no | `"T-7d..T+0"` | Time window on message timestamp. |
| `limit` | `int` | no | `10` | Max messages returned (server-capped at 50). |

### `content` format

```
slack_search(channel=#sre-oncall, query="OIDC rotation", time_range=T-24h..T+0):
Found 3 matches.

[#sre-oncall] 2026-04-22 00:25Z  @j.patel
  rotated OIDC signing key, terraform applied to all regions, looks clean. closing CHG-1891.

[#sre-oncall] 2026-04-22 00:52Z  @k.davis
  nice. auth latency looks normal. thanks.

[#sre-oncall] 2026-04-22 13:45Z  @oncall-bot
  PagerDuty: auth_svc_5xx_rate_cloud2 SEV-2 fired. 5min burn rate 8.7%.
```

### `data` format

```json
{
  "query_params": { ... },
  "total_matches": 3,
  "messages": [
    {
      "channel": "#sre-oncall",
      "timestamp": "2026-04-22T00:25:00Z",
      "author": "j.patel",
      "text": "rotated OIDC signing key, terraform applied to all regions, looks clean. closing CHG-1891.",
      "thread_ts": null
    },
    ...
  ]
}
```

### Edge cases

- Unknown channel → error with valid channel list.
- Zero matches → empty list, not an error.

---

## 6. `kb_search`

Search the internal knowledge base (Confluence-style wiki).

### Arguments

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | `str` | **yes** | — | Free-text search across title + body. |
| `limit` | `int` | no | `3` | Number of top matches to return (capped at 5). |

### `content` format

Top matches returned with **full markdown body** (docs are short; no separate `kb_read` tool needed).

```
kb_search(query="OIDC key rotation"):
Found 3 matches. Showing top 3 with full content.

============================================================
[1] runbooks/oidc-key-rotation (kb-42)  |  last edited 2026-01-15
============================================================
# OIDC Signing Key Rotation Runbook

...full markdown content of the doc...

============================================================
[2] terraform/best-practices (kb-17)  |  last edited 2026-03-02
============================================================
# Terraform Best Practices

...full markdown content...

============================================================
[3] incidents/2024-auth-outage (kb-9)  |  last edited 2024-06-03
============================================================
# Authentication outage -- retrospective

...full markdown content (note: old doc, may be stale)...
```

The `last edited` date is shown explicitly; agent must judge staleness.

### `data` format

```json
{
  "query_params": { ... },
  "total_matches": 3,
  "returned": 3,
  "docs": [
    {
      "id": "kb-42",
      "path": "runbooks/oidc-key-rotation",
      "title": "OIDC Signing Key Rotation Runbook",
      "last_edited": "2026-01-15T00:00:00Z",
      "body_md": "# OIDC Signing Key Rotation Runbook\n\n...",
      "word_count": 412
    },
    ...
  ]
}
```

### Edge cases

- Empty `query` → error; require something to search.
- Zero matches → empty list, not an error.
- Staleness is surfaced as a date, NOT a flag. Agent makes the call.

---

## 7. `submit_answer` (terminal pseudo-tool)

Not a real tool — it's the terminal action. Ends the episode, computes terminal reward.

### Arguments

| Name | Type | Required | Description |
|---|---|---|---|
| `root_cause` | `str` | **yes** | Paragraph describing what caused the incident. Scored against ground truth with string-matching + rubric. |
| `fix` | `str` | **yes** | Paragraph describing the remediation. Scored against ground truth. |

### Example

```json
{
  "tool_name": "submit_answer",
  "arguments": {
    "root_cause": "SRE j.patel applied CHG-1891 (OIDC signing key rotation) at 2026-04-22 00:15Z. The Terraform apply silently failed on cloud-2 due to state-lock contention with another concurrent run. cloud-2's sts-broker is still using the old public key; Okta now signs tokens with the new private key, so cloud-2 rejects all Acme JWTs with 'signature verification failed'. cloud-1 and cloud-3 received the rotation correctly and are healthy.",
    "fix": "Re-apply Terraform targeting cloud-2 only, to push the new public key into sts-broker. Do NOT roll back the rotation globally -- cloud-1 and cloud-3 are healthy with the new key."
  }
}
```

### Reward shape

Terminal reward breakdown (details in `REWARD.md`, written during P1):

| Component | Weight | Hits when... |
|---|---|---|
| Identifies `CHG-1891` | 0.25 | `"CHG-1891"` present in `root_cause` |
| Identifies cloud-2 as affected | 0.15 | `"cloud-2"` present and scoped correctly |
| Identifies state-lock failure mode | 0.20 | mentions state lock / silent failure |
| Identifies stale key as symptom | 0.15 | mentions old/stale public key, signature verification |
| Proposes correct scoped fix | 0.15 | mentions re-apply for cloud-2 |
| Avoids bad fix (global rollback) | 0.10 | does NOT advocate rolling back the rotation globally |

Max terminal reward = 1.0. Step-level rewards are separate and accumulate during the episode.

Returns `observation_type: "evaluation"`, `done: true`, and `reward` = the computed terminal reward. Details of each component shown in `content` for transparency.

---

## Tool count

**6 tools + submit_answer** (the terminal pseudo-action). Keeps `CloudSecAction.tool_name` to 7 valid values:

```
logs_search | trace_get | metric_query | ticket_search | slack_search | kb_search | submit_answer
```

No separate `kb_read` — `kb_search` returns full content for the top-N matches.
