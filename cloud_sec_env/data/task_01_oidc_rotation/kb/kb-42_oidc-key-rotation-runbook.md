---
id: kb-42
path: runbooks/oidc-key-rotation
title: "OIDC Signing Key Rotation Runbook"
last_edited: "2026-01-15T09:22:00Z"
author: security-platform-team
tags: [oidc, sts-broker, terraform, runbook]
---

# OIDC Signing Key Rotation Runbook

Quarterly hygiene for the OIDC signing key used by `sts-broker` to validate tenant JWTs.

## When to run

- Quarterly (Jan / Apr / Jul / Oct).
- After any suspected signing-key compromise.
- When a tenant reports unexpected token validation failures tied to `kid=` drift.

## Preconditions

- You are on the SRE oncall rotation.
- No other Terraform runs scheduled against `module.cloud_*.sts_broker_keys` in the next 30 min. Coordinate in `#infra-terraform`.
- `#sre-oncall` pinged with a heads-up.

## Procedure

1. **Generate** new RSA-2048 keypair in Vault: `vault write pki/keys/sts-broker type=rsa bits=2048`.
2. **Update tfvars** in `platform-infra/clouds/*/sts_broker.tfvars` with the new `signing_kid`.
3. **Apply per-cloud sequentially** (NOT in parallel): `cloud-1`, then `cloud-2`, then `cloud-3`. 10-min wait between each.
4. **Rotate Okta tenant signing key** via Okta admin console; update to the new private key.
5. **Verify** each cloud validates a fresh JWT under the new `kid` via `scripts/verify_sts_kid.sh <cloud>`.

## Known failure modes

### State-lock contention (HIGH IMPACT)

If anyone else is running a Terraform plan or apply against the same state bucket at the same time as your apply, your apply may **silently succeed with warnings** while actually not writing the new key config.

Symptoms:
- Terraform output shows `apply complete with warnings` (not `apply complete`).
- `warnings:` block in `terraform.log` references `state lock held by <other-user>`.
- Target cloud's `sts-broker` never reloads its JWKs config.
- Tokens signed with new private key fail validation on that cloud with `signature verification failed: kid=<old-kid> unknown`.

**How to confirm the silent failure:** run `terraform output -json | jq .sts_broker_key_id` on the affected cloud. If it shows the old kid, the apply silently no-op'd.

**How to fix:** re-apply Terraform targeting only the affected cloud's sts_broker_keys module:

```
terraform apply -target=module.cloud_N.sts_broker_keys
```

Do NOT roll back the global rotation -- the other clouds are healthy on the new key. A global rollback breaks them.

### Okta tenant key drift

If Okta signs with a new kid but clouds still serve old kid, all tenant logins will fail. Mitigation: invalidate the JWKs cache (`sts-broker admin flush-jwks`) and re-apply config.

### Cache warm-up after rotation

`sts-broker` caches JWKs for 5 min by default. First few requests post-rotation may fail with `kid_mismatch` -- wait 5 min or manually flush.

## Post-incident

- Update Okta admin notes with the new kid.
- File a change ticket closure (CHG-xxxx).
- Verify `sts.jwt_validation_failures` metric is flat on all 3 clouds for 60 min after rotation.

## Related

- [Terraform Best Practices](kb://terraform/best-practices)
- [OIDC Federation Overview](kb://architecture/oidc-federation)
- [Auth-svc 5xx Alert Runbook](kb://runbooks/auth-svc-5xx)
