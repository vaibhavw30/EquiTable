#!/usr/bin/env bash
# Fail if the Terraform-managed objects and their k8s/*.yaml twins disagree.
#
#   ./scripts/check-tf-yaml-parity.sh [kube-context]
#
# Run AFTER `terraform apply` against a cluster. The namespace, ServiceAccounts
# and ConfigMap are defined twice — in terraform/kubernetes.tf (ADR-029) and in
# k8s/ for scripts/k8s-up.sh — and two definitions of one object drift unless
# something checks them.
#
# Why not `kubectl diff`: it only reports fields the YAML sets that differ from
# the cluster. A key Terraform sets and the YAML has dropped is invisible to it
# (verified — deleting JINA_ENABLED from the YAML diffs clean). This compares
# the owned fields for exact equality instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT="${1:-$(kubectl config current-context)}"
NS="equitable"
fail=0

# YAML -> JSON with no cluster involved. A multi-document file comes out as a
# stream of objects, not a List.
yaml() { kubectl create --dry-run=client -o json -f "$REPO_ROOT/k8s/$1"; }
live() { kubectl --context "$CONTEXT" get "$@" -o json; }

compare() {  # name, jq filter, yaml-json, live-json
  local name="$1" filter="$2" want got
  want="$(jq -S "$filter" <<<"$3")"
  got="$(jq -S "$filter" <<<"$4")"
  if [ "$want" == "$got" ]; then
    echo "  ok    $name"
  else
    echo "  DRIFT $name"
    diff <(echo "$want") <(echo "$got") | sed 's/^</    yaml:     /; s/^>/    terraform:/' || true
    fail=1
  fi
}

echo "Terraform <-> k8s/ YAML parity (context: $CONTEXT)"

compare "ConfigMap equitable-config .data" '.data' \
  "$(yaml 10-configmap.yaml)" "$(live configmap equitable-config -n "$NS")"

# kubernetes.io/metadata.name is added by the API server to every namespace;
# it is in neither definition.
compare "Namespace $NS labels" '.metadata.labels | del(.["kubernetes.io/metadata.name"])' \
  "$(yaml 00-namespace.yaml)" "$(live namespace "$NS")"

SA_YAML="$(yaml 15-serviceaccounts.yaml)"
for sa in equitable-api equitable-refresh; do
  compare "ServiceAccount $sa automountServiceAccountToken" '.automountServiceAccountToken' \
    "$(jq --arg n "$sa" 'select(.metadata.name == $n)' <<<"$SA_YAML")" \
    "$(live serviceaccount "$sa" -n "$NS")"
done

if [ "$fail" -ne 0 ]; then
  echo
  echo "Terraform and k8s/ disagree. Change both, or the next 'terraform apply' and"
  echo "'scripts/k8s-up.sh' will keep overwriting each other."
  exit 1
fi
