---
id: kb-55
path: runbooks/incident-response
title: "Incident Response Playbook"
last_edited: "2026-02-28T10:00:00Z"
author: sre-platform-team
tags: [runbook, incident-response, oncall]
---

# Incident Response Playbook

Generic IR playbook for anyone on-call. Use this in conjunction with service-specific runbooks (e.g., `auth-svc-5xx`, `oidc-key-rotation`).

## Severities

| Sev | Definition | Response time |
|-----|-----------|---------------|
| SEV-1 | Outage affecting >25% of tenants | immediate |
| SEV-2 | Degradation affecting <25% of tenants, customer-impacting | <5 min |
| SEV-3 | Internal degradation, no customer impact | <30 min |
| SEV-4 | Noise, false alarm, low urgency | <24h |

## Incident flow

1. **Acknowledge** the page.
2. **Triage**: identify symptom, scope (which cloud/service/tenant).
3. **Communicate**: post in `#sre-oncall`. Create an incident Slack channel for SEV-1 / SEV-2.
4. **Investigate**: follow the service runbook. Rule out red herrings by scoping.
5. **Mitigate**: do the minimum change that stops customer pain. Keep full fix for after.
6. **Resolve**: verify metrics recovered. Close the incident ticket.
7. **Post-mortem**: for SEV-1 / SEV-2, blameless retro within 5 business days.

## Scoping discipline

Always scope queries to the *alerting* cloud first. Running broad queries
across all clouds will flood you with unrelated signal (especially if
another cloud has a coincident unrelated issue -- common during peak hours).

## Common anti-patterns

- **Premature global action.** Don't roll back a cross-cloud change
  just because one cloud has symptoms. Scope first.
- **Over-trusting human confirmations.** "Someone closed CHG-xxxx and said
  it looked clean" is a hypothesis, not a verified fact. Check metrics.
- **Chasing the first-fired red herring.** Multiple alerts near the same
  time are often unrelated. Cross-check timing and scope.

## Timing

Start your investigation timer on page ack. Log your decision points.
(For the retro.)

## Related

- [Auth-svc 5xx Runbook](kb://runbooks/auth-svc-5xx)
- [OIDC Key Rotation Runbook](kb://runbooks/oidc-key-rotation)
- [Terraform Best Practices](kb://terraform/best-practices)
