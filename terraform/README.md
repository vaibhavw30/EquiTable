# Terraform — EquiTable

Infrastructure as code for the namespace-scoped Kubernetes configuration and MongoDB Atlas.

## What Terraform owns, and what it does not

| Owned by Terraform | Owned by `kubectl` / `k8s-up.sh` | Owned by neither |
|---|---|---|
| Namespace | Deployment, Service, Ingress, HPA, PDB | The Secret |
| ServiceAccounts | CronJob | |
| ConfigMap | NetworkPolicies | |
| Atlas IP access list | kind cluster, Calico, ingress-nginx | |
| Atlas cluster (import-guarded) | | |

Three deliberate exclusions:

**The kind cluster.** `scripts/k8s-up.sh` already creates it. A Terraform-managed cluster would be
a second source of truth for the same object, and the two would drift.

**Workload manifests.** They change with the application and read better as Kubernetes YAML than as
HCL transliterations of the same fields. More concretely, `kubernetes_manifest` requires a
*reachable cluster at plan time*, which would make the `terraform plan` CI job depend on a live
cluster — defeating the point of gating changes on a plan.

**The Secret.** Terraform state stores values in **plaintext**. A `kubernetes_secret` resource
would write every API key into the state file, and with the S3 backend into a bucket. The Secret is
created from `backend_ml/.env` at apply time instead (ADR-028).

## Usage

```bash
terraform init
terraform plan     # against the local kind cluster
terraform apply
```

The provider pins `config_context = "kind-equitable"` rather than using whatever kubectl context
happens to be current — an apply landing on the wrong cluster is the most expensive mistake
available here.

## MongoDB Atlas — read before enabling

`var.manage_atlas` defaults to **false**, and that default is load-bearing.

The Atlas project and cluster already exist and hold production data. Applying without state that
already describes them makes Terraform plan to **create** a cluster it believes is missing.
Reconciling that against a live database is how people lose one.

Import first, and read the plan:

```bash
export TF_VAR_manage_atlas=true
export TF_VAR_atlas_public_key=...   TF_VAR_atlas_private_key=...
export TF_VAR_atlas_project_id=...

terraform import mongodbatlas_advanced_cluster.equitable <project_id>-<cluster_name>
terraform plan   # MUST say "No changes" for the cluster before you apply
```

A plan proposing to create or replace the cluster means the import did not match reality. Stop and
fix the import — do not apply. `prevent_destroy = true` is the backstop, not the plan.

`var.atlas_instance_size` is validated against `M0`/`M2`/`M5`. M0 is free; **M2 is ~$9/month**, so a
paid tier is an explicit reviewable change rather than an edit nobody notices.

## Remote state

`backend.tf` is **commented out by default**. Local state keeps `terraform plan` working offline
for review, and does not create billable AWS resources for anyone who clones this repo.

Local state is fine for one operator on one laptop. It is **not** fine the moment a second person
or a CI job can apply — concurrent applies against unlocked state corrupt it. The bootstrap
commands are in `backend.tf`; note that bucket versioning is not optional, because state is the
only record of what Terraform believes exists.

Locking uses S3's native conditional writes (`use_lockfile`, Terraform ≥ 1.11), which replaces the
DynamoDB lock table the older pattern required.

## CI

`.github/workflows/terraform.yml` runs on every PR that touches `terraform/`, the three YAML twins
(`k8s/00-namespace.yaml`, `10-configmap.yaml`, `15-serviceaccounts.yaml`), or the parity script
(ADR-032). It holds no credentials and touches no real environment:

1. `terraform fmt -check` and `terraform validate`.
2. On a throwaway kind cluster named `equitable` (so the pinned `kind-equitable` context is real):
   plan → fail if the plan contains any Atlas resource → apply → re-plan must be a no-op →
   `scripts/check-tf-yaml-parity.sh`.

The namespace, ServiceAccounts and ConfigMap are defined both here and in `k8s/`. **Change both.**
Run the parity check locally after an apply:

```bash
../scripts/check-tf-yaml-parity.sh kind-equitable
```

If you add a provider or bump a version, refresh the lock for CI's platform as well as your own:

```bash
terraform providers lock -platform=linux_amd64 -platform=darwin_arm64 -platform=darwin_amd64
```

## What is not verified

`terraform validate` passes and the configuration is formatted. The Kubernetes resources are
planned, applied and re-planned in CI on every change. **`terraform apply` has not been run against
Atlas**, because doing so safely requires the import above and Atlas API credentials. The Atlas
resources are written and validated but not applied; CI only asserts they stay out of the plan.
