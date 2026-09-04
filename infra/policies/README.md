# Infrastructure policy templates

- `container-security.rego` is a Conftest/OPA policy for Kubernetes workload manifests. It rejects mutable image tags and workloads without the restricted container baseline.
- `object-store-writer-policy.example.json` is an S3-compatible least-privilege shape for a raw-evidence writer. Replace the non-routable bucket placeholder and add provider-specific KMS conditions. It intentionally grants no delete action.
- `postgres-roles.sql` is the role policy for the normalized architectural reference schema under `fda_intel`.
- `postgres-runtime-roles.sql` is the runnable SQLAlchemy `public`-schema policy, including owner-scoped chat, versioned chunk embeddings, and the case-scoped Agent OS control plane. Apply it only after the one-time ORM bootstrap and `20260904_agent_os_control_plane.sql` forward migration. Both files create NOLOGIN group roles; bind short-lived workload identities separately and never embed login passwords.

Example checks:

```powershell
kubectl kustomize infra/deployment/kubernetes/base | conftest test --policy infra/policies -
```

Platform-native admission policy remains authoritative. Reconcile these examples with corporate standards and test denied cases in staging.
