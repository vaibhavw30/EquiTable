provider "kubernetes" {
  # Reads the local kubeconfig rather than embedding credentials. `config_context`
  # is pinned explicitly so a `terraform apply` can never land on whatever cluster
  # happens to be current — the single most expensive mistake available here.
  config_path    = var.kubeconfig_path
  config_context = "kind-${var.cluster_name}"
}

provider "mongodbatlas" {
  public_key  = var.atlas_public_key
  private_key = var.atlas_private_key
}
