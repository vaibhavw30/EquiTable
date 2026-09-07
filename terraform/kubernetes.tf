# ─────────────────────────────────────────────────────────────────────────────
# Namespace-scoped configuration.
#
# Terraform owns the namespace, the ServiceAccounts, and the ConfigMap — the
# things that describe the environment. It deliberately does NOT own the
# Deployment, Service, Ingress, HPA, CronJob or NetworkPolicies: those live as
# YAML in k8s/ and are applied with kubectl.
#
# The split is on purpose. Workload manifests change with the application and
# read better as Kubernetes YAML than as HCL transliterations of the same
# fields, and `kubernetes_manifest` requires a reachable cluster at PLAN time,
# which would break the `terraform plan` CI job (ADR-029). Environment config
# changes rarely and benefits from being reviewed as a diff with the Atlas rules
# next to it.
#
# The Secret is owned by neither: it is created from .env at apply time so real
# credentials never enter state. Terraform state stores values in PLAINTEXT, so
# a `kubernetes_secret` resource would write every API key into the state file
# and, with the S3 backend, into a bucket (ADR-028).
# ─────────────────────────────────────────────────────────────────────────────

resource "kubernetes_namespace" "equitable" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/name" = "equitable"
      "name"                   = var.namespace
    }
  }
}

resource "kubernetes_service_account" "api" {
  metadata {
    name      = "equitable-api"
    namespace = kubernetes_namespace.equitable.metadata[0].name
  }
  # Neither workload calls the Kubernetes API. An unused token mounted into a
  # pod that scrapes untrusted third-party sites is pure downside.
  automount_service_account_token = false
}

resource "kubernetes_service_account" "refresh" {
  metadata {
    name      = "equitable-refresh"
    namespace = kubernetes_namespace.equitable.metadata[0].name
  }
  automount_service_account_token = false
}

resource "kubernetes_config_map" "equitable" {
  metadata {
    name      = "equitable-config"
    namespace = kubernetes_namespace.equitable.metadata[0].name
  }

  # Non-secret only. Anything here is readable by anyone with get on ConfigMaps.
  data = {
    DATABASE_NAME = var.database_name

    REFRESH_MAX_SOURCES     = tostring(var.refresh_max_sources)
    REFRESH_MAX_COST_USD    = format("%.2f", var.refresh_max_cost_usd)
    REFRESH_FRESHNESS_HOURS = tostring(var.refresh_freshness_hours)

    # Scraper fallback chain (ADR-021). Firecrawl is paid; off is what keeps
    # scraping at $0.
    JINA_ENABLED               = "true"
    FIRECRAWL_FALLBACK_ENABLED = "false"

    LANGCHAIN_TRACING_V2 = "true"
    LANGCHAIN_PROJECT    = "equitable-refresh-agent"
  }
}
