variable "cluster_name" {
  description = "Name of the local kind cluster."
  type        = string
  default     = "equitable"
}

variable "namespace" {
  description = "Kubernetes namespace holding the EquiTable workloads."
  type        = string
  default     = "equitable"
}

variable "database_name" {
  description = "MongoDB database name used by both the API and the refresh agent."
  type        = string
  default     = "equitable"
}

# ── Refresh-run knobs (mirrored into the ConfigMap) ─────────────────────────

variable "refresh_max_sources" {
  description = "Maximum pantries refreshed per run."
  type        = number
  default     = 25

  validation {
    condition     = var.refresh_max_sources > 0 && var.refresh_max_sources <= 500
    error_message = "refresh_max_sources must be between 1 and 500."
  }
}

variable "refresh_max_cost_usd" {
  description = "Per-run Gemini budget in USD. Enforced in-process by CostTracker."
  type        = number
  default     = 0.50

  validation {
    # A budget of 0 disables extraction entirely rather than making it free —
    # every source would come back skipped_budget. Catch that at plan time.
    condition     = var.refresh_max_cost_usd > 0
    error_message = "refresh_max_cost_usd must be greater than 0; a zero budget skips every source."
  }
}

variable "refresh_freshness_hours" {
  description = "Only pantries staler than this many hours are refresh candidates."
  type        = number
  default     = 24
}

# ── MongoDB Atlas ───────────────────────────────────────────────────────────

variable "manage_atlas" {
  description = <<-EOT
    Whether Terraform manages MongoDB Atlas resources.

    Defaults to FALSE, and that default is load-bearing. The Atlas project and
    cluster already exist and hold production data. Applying these resources
    without first running `terraform import` would make Terraform believe it
    must CREATE them, and reconciling that against reality risks destroying a
    live database.

    Set to true only after importing. See terraform/README.md.
  EOT
  type        = bool
  default     = false
}

variable "atlas_public_key" {
  description = "MongoDB Atlas API public key. Only needed when manage_atlas = true."
  type        = string
  default     = ""
  sensitive   = true
}

variable "atlas_private_key" {
  description = "MongoDB Atlas API private key. Only needed when manage_atlas = true."
  type        = string
  default     = ""
  sensitive   = true
}

variable "atlas_project_id" {
  description = "Existing Atlas project ID. Only needed when manage_atlas = true."
  type        = string
  default     = ""
}

variable "atlas_allowed_cidrs" {
  description = <<-EOT
    CIDR blocks permitted to reach the Atlas cluster, as cidr => description.

    ADR-019 records the current reality: this is 0.0.0.0/0, because the Fargate
    task has a dynamic public IP and allow-listing it would require a NAT
    Gateway (~$32/mo against a ~$1-2/mo job). Security rests on the DB password
    plus TLS. Encoding it here makes the exposure reviewable in a diff instead
    of invisible in a console.
  EOT
  type        = map(string)
  default = {
    "0.0.0.0/0" = "Open — dynamic Fargate/local IPs. See ADR-019. Tighten via PrivateLink (M10+)."
  }
}

variable "kubeconfig_path" {
  description = "Path to the kubeconfig Terraform should use."
  type        = string
  default     = "~/.kube/config"
}

variable "atlas_cluster_name" {
  description = "Name of the Atlas cluster. Only used when manage_atlas = true."
  type        = string
  default     = "equitable"
}

variable "atlas_region" {
  description = "Atlas region name (e.g. US_EAST_1). Must match the existing cluster when importing."
  type        = string
  default     = "US_EAST_1"
}

variable "atlas_backing_provider" {
  description = "Backing cloud provider for a TENANT (shared/free) cluster."
  type        = string
  default     = "AWS"
}

variable "atlas_instance_size" {
  description = <<-EOT
    Atlas instance size. M0 is the free tier.

    Anything other than M0 starts billing immediately — M2 is ~$9/month. Kept as
    a variable with a free default so a paid tier is an explicit, reviewable
    change rather than an edit someone makes without noticing the cost.
  EOT
  type        = string
  default     = "M0"

  validation {
    condition     = contains(["M0", "M2", "M5"], var.atlas_instance_size)
    error_message = "atlas_instance_size must be M0 (free), M2, or M5. Larger tiers need a deliberate change here."
  }
}
