output "namespace" {
  description = "Namespace holding the EquiTable workloads."
  value       = kubernetes_namespace.equitable.metadata[0].name
}

output "config_map_name" {
  description = "ConfigMap consumed by both the API Deployment and the refresh CronJob."
  value       = kubernetes_config_map.equitable.metadata[0].name
}

output "service_accounts" {
  description = "ServiceAccounts created for the two workloads."
  value = {
    api     = kubernetes_service_account.api.metadata[0].name
    refresh = kubernetes_service_account.refresh.metadata[0].name
  }
}

output "atlas_managed" {
  description = "Whether Terraform is managing Atlas resources (see atlas.tf before enabling)."
  value       = var.manage_atlas
}

output "next_step" {
  description = "Workload manifests are applied with kubectl, not Terraform — see kubernetes.tf."
  value       = "kubectl apply -f k8s/ (excluding 11-secret.example.yaml)"
}
