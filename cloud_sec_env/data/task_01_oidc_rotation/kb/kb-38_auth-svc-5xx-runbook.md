---
id: kb-38
path: runbooks/auth-svc-5xx
title: "auth-svc 5xx rate alert -- Runbook"
last_edited: "2026-02-10T11:05:00Z"
author: sre-platform-team
tags: [runbook, auth-svc, alert]
---

# auth-svc 5xx rate alert -- Runbook

Fires when `auth-svc` HTTP 5xx rate exceeds **5%** for 30 minutes on any cloud.

## First 5 minutes

1. Confirm which cloud the alert scopes to (label: `cloud=cloud-N`).
2. Open the cloud-scoped Grafana dashboard: `grafana://auth-svc-health`.
3. Check upstream dependencies: `sts-broker`, `policy-svc`, `api-gateway`.

## Usual suspects (in order of frequency)

### 1. sts-broker validation failures

If `auth-svc` returns 5xx and traces show failures at the `sts-broker` hop,
it's token validation. Check:

- JWKs cache: `sts-broker admin jwks-info`.
- Recent changes to sts-broker config (Terraform).
- Okta tenant signing key status.

### 2. policy-svc timeouts

`auth-svc` calls `policy-svc` after validation. If policy-svc is slow,
auth-svc times out upstream -> 504. Check policy-svc metrics.

### 3. Downstream DB or cache saturation

Check `sts-broker` Redis connection pool exhaustion. Known flaky dependency;
can contribute ~0.5-1% baseline 5xx even when healthy.

## Scoping discipline

Always scope investigations to the alerting cloud first. Other clouds with the
same service may look healthy and distract. Do NOT conclude "it's a global
problem" without metric data from the other clouds.

## When sts-broker is the prime suspect

- Check `sts.jwt_validation_failures` -- step changes correlate with
  config changes.
- Cross-reference recent Terraform applies via `ticket_search type=CHG`.
- Check `#infra-terraform` for any state-lock chatter around the apply window.

## Escalation

After 30 min of active investigation without a root cause, page the
on-call platform engineer. SEV-2+ customer-impacting should not wait past
45 min total time-to-engagement.

## Related

- [OIDC Key Rotation Runbook](kb://runbooks/oidc-key-rotation)
- [Terraform Best Practices](kb://terraform/best-practices)
- [Incident Response Playbook](kb://runbooks/incident-response)
