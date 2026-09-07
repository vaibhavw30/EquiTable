terraform {
  # 1.11 introduced native S3 state locking (`use_lockfile`), which is what lets
  # backend.tf drop the DynamoDB lock table entirely. Pinning the floor here
  # means a too-old CLI fails with a clear message instead of silently running
  # unlocked.
  required_version = ">= 1.11"

  required_providers {
    # Pinned to a major version with ~> so patch/minor updates are allowed but a
    # breaking major is not. Provider majors routinely rename resources.
    #
    # Deliberately NOT using a `kind` provider. The spec allows managing "cluster
    # or namespace"; namespace is the right choice here because scripts/k8s-up.sh
    # already creates the cluster, and a Terraform-managed kind cluster would be a
    # second source of truth for the same object — two ways to create it, two ways
    # for them to disagree. Terraform owns what the script does not: the
    # namespace-scoped config and MongoDB Atlas.
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.38"
    }
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 1.30"
    }
  }
}
