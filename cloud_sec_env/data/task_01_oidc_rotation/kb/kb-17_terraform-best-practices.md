---
id: kb-17
path: terraform/best-practices
title: "Terraform Best Practices"
last_edited: "2026-03-02T14:10:00Z"
author: platform-team
tags: [terraform, infrastructure, best-practices]
---

# Terraform Best Practices

General guidance for anyone writing or applying Terraform across our clouds. If you're not a platform engineer, read the first three sections at least.

## 1. Always target specific modules for cross-cloud changes

Running a bare `terraform apply` against a workspace with multiple clouds can apply changes you didn't intend to. Prefer:

```
terraform apply -target=module.cloud_1.<resource>
```

Better yet, isolate each cloud into its own workspace to avoid the problem entirely.

## 2. Coordinate in `#infra-terraform` before applies

Slack-post your plan or apply before running it if you're touching shared state (e.g., anything under `module.cloud_*`). This avoids state-lock contention and apply conflicts.

State locks are held per-workspace on S3 + DynamoDB. If two plans run simultaneously:
- Second one gets blocked (DynamoDB conditional write fails).
- Terraform retries up to 3 times over ~2 minutes.
- If still locked, the second apply **may exit with warnings but no error**, depending on provider version and retry config.

This is a known footgun. Coordinate before applying.

## 3. Review plan output before apply

Seriously. A plan that shows `0 to add, 0 to change, 0 to destroy` means the apply will no-op. A plan with `N to change` is where you look twice before approving.

## 4. Standard sequencing for rotations and migrations

When rolling a change across multiple clouds:
1. Apply to one cloud.
2. Wait 10+ minutes and verify metrics.
3. Only then apply to the next cloud.

Parallel applies across clouds should be avoided except for truly independent resources.

## 5. Terraform output warnings are not always harmless

If `terraform apply` completes with `warnings`, read them. Common sources:
- Deprecated argument (usually safe).
- State-lock retry exhausted (NOT safe -- apply may have been a partial no-op).
- Provider-level transient failure (may need re-apply).

## 6. Don't commit `terraform.log` or `*.tfstate`

`.gitignore` already excludes them. But double-check before pushing.

## See also

- [OIDC Key Rotation Runbook](kb://runbooks/oidc-key-rotation)
- [Incident Response Playbook](kb://runbooks/incident-response)
