---
id: kb-09
path: incidents/2024-auth-outage
title: "Authentication outage -- retrospective (June 2024)"
last_edited: "2024-06-03T17:40:00Z"
author: j.patel
tags: [incident, retrospective, auth, 2024]
---

# Authentication outage -- retrospective (2024-06-03)

**STATUS:** Closed. Kept for historical reference.

> **NOTE:** This retro references the legacy `nimbus-jwt` library which was
> retired in October 2024 and replaced by `sts-broker`. Log message patterns
> shown here no longer match production logs. Use with care as a historical
> reference only.

## Summary

On 2024-06-03 at 08:22 UTC, cloud-1 `auth-gateway` (legacy service, now merged into api-gateway) started returning 503 to all tenants for approximately 18 minutes.

## Root cause

A deploy of `nimbus-jwt` 3.11.0 introduced a regression where the library's
LRU cache for Okta public keys had its capacity set to 0. The cache was
instantiated but every lookup missed and re-fetched from Okta, saturating
the Okta rate limit.

## Symptoms to look for (legacy)

- `nimbus-jwt: fetching JWKS from okta` at >100 rps in auth-gateway logs.
- `auth-gateway 503 upstream_ratelimited` in api-gateway logs.
- Okta-side rate-limit alerts fired at the same time.
- Metric `nimbus_jwt.jwks_cache.hit_ratio = 0.0`.

## Resolution

Rolled back `nimbus-jwt` to 3.10.4 via canary revert. Upstream fix shipped
in 3.11.1 the following week.

## Lessons learned

- Always verify cache hit ratios in staging before merging library upgrades.
- Rate limits on upstream IdPs are a real risk; engineer for graceful
  degradation (pre-fetched and pinned keys).

## Relevance to current state

Minimal. `sts-broker` (the successor to `auth-gateway`) caches JWKs via a
different mechanism and is no longer coupled to `nimbus-jwt`. The failure
modes described above cannot occur in current production.

## Related

- [Auth-svc 5xx Runbook](kb://runbooks/auth-svc-5xx) (current)
- [OIDC Federation Overview](kb://architecture/oidc-federation)
