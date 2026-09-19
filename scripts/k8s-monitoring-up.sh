#!/usr/bin/env bash
# Install Prometheus + Grafana + Pushgateway into the kind cluster and wire the
# EquiTable dashboard, ServiceMonitor and alert rules (ADR-030, ADR-031).
#
#   ./scripts/k8s-monitoring-up.sh      # after ./scripts/k8s-up.sh
#
# Idempotent. Everything is free and in-cluster; nothing leaves the laptop.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER="${CLUSTER:-equitable}"
MON_NS="monitoring"
MON_DIR="$REPO_ROOT/k8s/monitoring"

# Pinned: a chart bump can rename services or flip defaults (the ServiceMonitor
# selector behaviour has changed before), so upgrades are deliberate.
KPS_VERSION="91.4.1"
PUSHGATEWAY_VERSION="3.8.0"

log() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

for bin in kubectl helm; do
  command -v "$bin" >/dev/null 2>&1 || { echo "ERROR: '$bin' not found on PATH"; exit 1; }
done
kubectl config use-context "kind-${CLUSTER}" >/dev/null

log "Adding the prometheus-community Helm repo"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update prometheus-community >/dev/null

kubectl create namespace "$MON_NS" --dry-run=client -o yaml | kubectl apply -f -

# Random Grafana admin password, generated once and kept in-cluster. Never a
# committed default.
if ! kubectl get secret grafana-admin -n "$MON_NS" >/dev/null 2>&1; then
  log "Generating Grafana admin credentials"
  kubectl create secret generic grafana-admin -n "$MON_NS" \
    --from-literal=admin-user=admin \
    --from-literal=admin-password="$(openssl rand -base64 18)"
fi

log "Installing kube-prometheus-stack $KPS_VERSION (Prometheus, Grafana, kube-state-metrics)"
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --version "$KPS_VERSION" --namespace "$MON_NS" \
  -f "$MON_DIR/kube-prometheus-stack-values.yaml" --wait --timeout 10m

log "Installing Pushgateway $PUSHGATEWAY_VERSION"
helm upgrade --install pushgateway prometheus-community/prometheus-pushgateway \
  --version "$PUSHGATEWAY_VERSION" --namespace "$MON_NS" \
  -f "$MON_DIR/pushgateway-values.yaml" --wait --timeout 5m

log "Applying ServiceMonitor, alert rules and dashboard"
kubectl apply -f "$MON_DIR/api-servicemonitor.yaml"
kubectl apply -f "$MON_DIR/prometheus-rules.yaml"
# The Grafana sidecar loads any ConfigMap labelled grafana_dashboard=1.
kubectl create configmap equitable-dashboard -n "$MON_NS" \
  --from-file="$MON_DIR/dashboards/equitable-scraper.json" \
  --dry-run=client -o yaml \
  | kubectl label --local -f - grafana_dashboard=1 -o yaml \
  | kubectl apply -f -

# The API only listens on its metrics port when METRICS_PORT is set, and the
# refresh CronJob only pushes when PUSHGATEWAY_URL is — both are in the app
# manifests. Re-apply them in case this runs against an older deployment.
kubectl apply -f "$REPO_ROOT/k8s/20-api-deployment.yaml" \
              -f "$REPO_ROOT/k8s/30-api-service.yaml" \
              -f "$REPO_ROOT/k8s/60-refresh-cronjob.yaml" \
              -f "$REPO_ROOT/k8s/70-networkpolicy.yaml"

log "Done"
kubectl get pods -n "$MON_NS"
cat <<'EOF'

Grafana:     kubectl port-forward -n monitoring svc/grafana 3000:80
             open http://localhost:3000/d/equitable-scraper
             user: admin   password:
               kubectl get secret grafana-admin -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d; echo
Prometheus:  kubectl port-forward -n monitoring svc/kps-prometheus 9090:9090
             open http://localhost:9090/targets   (equitable-api and pushgateway should be UP)

Put numbers on the dashboard by running a refresh:
  kubectl create job -n equitable --from=cronjob/equitable-refresh manual-$(date +%s)
EOF
