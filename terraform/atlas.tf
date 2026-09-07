# ─────────────────────────────────────────────────────────────────────────────
# MongoDB Atlas.
#
# GUARDED BY var.manage_atlas, WHICH DEFAULTS TO FALSE. Read this before
# flipping it.
#
# The Atlas project and cluster already exist and hold production data. If
# Terraform applies these resources without state that already describes them,
# it will plan to CREATE a cluster it thinks is missing — and reconciling that
# against a live database is how people lose one.
#
# The safe sequence is import-then-plan, and the plan must be read before it is
# applied:
#
#   export TF_VAR_manage_atlas=true
#   export TF_VAR_atlas_public_key=...  TF_VAR_atlas_private_key=...
#   export TF_VAR_atlas_project_id=...
#
#   terraform import mongodbatlas_advanced_cluster.equitable <project_id>-<cluster_name>
#   terraform plan     # MUST show "No changes" for the cluster before you apply
#
# A plan that proposes to create or replace the cluster means the import did not
# match reality. Stop and fix the import; do not apply.
# ─────────────────────────────────────────────────────────────────────────────

resource "mongodbatlas_project_ip_access_list" "allowed" {
  for_each = var.manage_atlas ? var.atlas_allowed_cidrs : {}

  project_id = var.atlas_project_id
  cidr_block = each.key
  comment    = each.value
}

resource "mongodbatlas_advanced_cluster" "equitable" {
  count = var.manage_atlas ? 1 : 0

  project_id     = var.atlas_project_id
  name           = var.atlas_cluster_name
  cluster_type   = "REPLICASET"
  backup_enabled = false # M0 free tier does not support backup

  replication_specs {
    region_configs {
      priority              = 7
      provider_name         = "TENANT"
      backing_provider_name = var.atlas_backing_provider
      region_name           = var.atlas_region

      electable_specs {
        # M0 is the free tier. Changing this to any paid tier starts billing
        # immediately, so it is a variable with a free default rather than a
        # value someone edits in place without noticing.
        instance_size = var.atlas_instance_size
      }
    }
  }

  lifecycle {
    # Last line of defence. A destroy of this resource destroys the production
    # database; `terraform destroy` will refuse rather than proceed. Removing
    # this block must be a deliberate, reviewed act.
    prevent_destroy = true
  }
}
