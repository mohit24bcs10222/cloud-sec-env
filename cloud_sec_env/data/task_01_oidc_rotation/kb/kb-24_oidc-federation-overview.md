---
id: kb-24
path: architecture/oidc-federation
title: "OIDC Federation Overview"
last_edited: "2025-11-22T08:30:00Z"
author: security-platform-team
tags: [oidc, architecture, federation, sts-broker]
---

# OIDC Federation Overview

How NimbusGuard federates with customer identity providers (Okta, Azure AD, Ping) over OIDC.

## The model in one diagram

```
Customer IdP (Okta / Azure AD / Ping)
    │
    │  1. User authenticates; IdP issues JWT signed with IdP's private key.
    │
    ▼
NimbusGuard api-gateway
    │
    │  2. Forwards JWT to auth-svc.
    │
    ▼
auth-svc
    │
    │  3. Calls sts-broker to validate the JWT.
    │
    ▼
sts-broker
    │
    │  4. Verifies signature using cached JWKs (IdP public keys).
    │  5. Returns validation result.
    │
    ▼
auth-svc (returns session token)
```

## Key validation flow details

When a JWT arrives at `sts-broker`, the following happens:

1. Parse the JWT header. Extract the `kid` claim.
2. Look up the `kid` in the local JWKs cache (5-min TTL).
3. If cache miss, fetch the JWKs set from the IdP and re-populate.
4. Verify signature using the matching public key.
5. Validate claims: `iss`, `aud`, `exp`, `nbf`, `iat`.
6. Return decoded claims or a validation failure.

## Common failure modes

- **`kid` not in JWKs set**: signature check fails immediately. Logs show
  `signature verification failed: kid=<kid> unknown`. Usually means IdP
  rotated its signing key but our cache is stale (or our config doesn't
  know the new kid).
- **Clock skew**: `exp` or `nbf` validation fails if our clock is off by
  more than 60s from IdP. Rare, but happens during clock-service outages.
- **Revoked token**: IdP revokes a session; our validation still succeeds
  until the token expires. We depend on IdP-side revocation; NimbusGuard
  does not implement its own JWT revocation store.

## Key rotation

Both our signing keys (for our own-issued tokens) and IdP-side signing keys
rotate. See [OIDC Key Rotation Runbook](kb://runbooks/oidc-key-rotation)
for the signing-key rotation procedure on our side.

## Tenant isolation

Each tenant's IdP config lives in `sts-broker`'s per-tenant config map:
`sts-broker-config/tenants/<tenant_id>.yaml`. Tenant-specific claims
(issuer URL, audience, trusted kids) are pinned here.

## Related

- [OIDC Key Rotation Runbook](kb://runbooks/oidc-key-rotation)
- [Auth-svc 5xx Runbook](kb://runbooks/auth-svc-5xx)
