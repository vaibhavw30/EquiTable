#!/usr/bin/env bash
# Stand up the whole EquiTable stack on a local kind cluster, from nothing.
#
#   ./scripts/k8s-up.sh
#
# Idempotent: safe to re-run. Requires docker, kind, kubectl, and a populated
# backend_ml/.env (the Secret is built from it and is never committed).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER="${CLUSTER:-equitable}"
NAMESPACE="${NAMESPACE:-equitable}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/backend_ml/.env}"

# MUST match `networking.podSubnet` in k8s/kind/cluster.yaml. Calico's IP pool is
# pinned to this below; if the two disagree, pod networking breaks in ways that
# look like a policy or DNS fault.
POD_CIDR="${POD_CIDR:-10.244.0.0/16}"

log() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

# ── Preflight ───────────────────────────────────────────────────────────────
for bin in docker kind kubectl; do
  command -v "$bin" >/dev/null 2>&1 || { echo "ERROR: '$bin' not found on PATH"; exit 1; }
done

docker info >/dev/null 2>&1 || {
  echo "ERROR: the Docker daemon is not running. Start OrbStack or Docker Desktop first."
  exit 1
}

[ -f "$ENV_FILE" ] || {
  echo "ERROR: $ENV_FILE not found."
  echo "Copy backend_ml/.env.example to backend_ml/.env and fill in real values."
  exit 1
}

# ── Cluster ─────────────────────────────────────────────────────────────────
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  log "kind cluster '$CLUSTER' already exists — reusing it"
else
  log "Creating kind cluster '$CLUSTER'"
  # No --wait here: the cluster is created with disableDefaultCNI, so nodes cannot
  # reach Ready until Calico is installed below. Waiting would burn the full
  # timeout on every run and print an alarming (but meaningless) warning.
  kind create cluster --config "$REPO_ROOT/k8s/kind/cluster.yaml"
fi

kubectl config use-context "kind-${CLUSTER}"

# ── CNI ─────────────────────────────────────────────────────────────────────
# The cluster is created with disableDefaultCNI, so nodes stay NotReady until a
# CNI is installed. Calico is used instead of kind's kindnet because kindnet
# does not enforce NetworkPolicy — with it, k8s/70-networkpolicy.yaml would be
# accepted and silently ignored.
if kubectl get daemonset calico-node -n kube-system >/dev/null 2>&1; then
  log "Calico already installed"
else
  log "Installing Calico (CNI + NetworkPolicy enforcement)"
  # Calico's default IP pool is 192.168.0.0/16, which collides with the Docker
  # bridge subnets OrbStack hands out for kind node IPs (192.168.x.x). The pool
  # must be pinned to the same CIDR as the cluster's podSubnet — see the note in
  # k8s/kind/cluster.yaml for the failure this causes.
  CALICO_MANIFEST="$(mktemp)"
  curl -fsSL "https://raw.githubusercontent.com/projectcalico/calico/v3.30.2/manifests/calico.yaml" -o "$CALICO_MANIFEST"
  python3 - "$CALICO_MANIFEST" "$POD_CIDR" <<'PYEOF'
import sys
path, cidr = sys.argv[1], sys.argv[2]
text = open(path).read()
# The stock manifest ships these two lines commented out. Uncomment by removing
# the "# " while preserving indentation, and set our CIDR.
before = text
text = text.replace("# - name: CALICO_IPV4POOL_CIDR", "- name: CALICO_IPV4POOL_CIDR", 1)
text = text.replace('#   value: "192.168.0.0/16"', '  value: "%s"' % cidr, 1)
if text == before:
    sys.exit("ERROR: could not patch CALICO_IPV4POOL_CIDR — the upstream manifest changed shape")
open(path, "w").write(text)
print("  patched CALICO_IPV4POOL_CIDR -> %s" % cidr)
PYEOF
  kubectl apply -f "$CALICO_MANIFEST"
  rm -f "$CALICO_MANIFEST"
fi
log "Waiting for nodes to become Ready"
kubectl wait --for=condition=Ready nodes --all --timeout=300s

# ── Ingress controller ──────────────────────────────────────────────────────
if kubectl get namespace ingress-nginx >/dev/null 2>&1; then
  log "ingress-nginx already installed"
else
  log "Installing ingress-nginx"
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.13.0/deploy/static/provider/kind/deploy.yaml
fi
# Pin the controller to the node that actually has the host port mappings.
#
# k8s/kind/cluster.yaml labels the control-plane node `ingress-ready=true` and
# publishes host ports 80/443 from it. The controller declares hostPort 80/443
# and tolerates the control-plane taint — but ingress-nginx v1.13.0's kind
# manifest no longer sets a matching nodeSelector, so the scheduler is free to
# place it on the worker, where nothing is published to the host. The symptom is
# a controller that is Running and Ready while every request from the host is
# refused.
log "Pinning ingress-nginx to the ingress-ready node"
kubectl patch deployment ingress-nginx-controller -n ingress-nginx --type=strategic \
  -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/os":"linux","ingress-ready":"true"}}}}}'

log "Waiting for ingress-nginx to be ready"
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=300s

# ── metrics-server ──────────────────────────────────────────────────────────
# The HPA reads pod CPU from the metrics API. kind ships no metrics-server, so
# without this the HPA reports <unknown>/70% forever and never scales.
# --kubelet-insecure-tls is required because kind's kubelet serving certs are
# self-signed and not in the cluster CA.
if kubectl get deployment metrics-server -n kube-system >/dev/null 2>&1; then
  log "metrics-server already installed"
else
  log "Installing metrics-server (required by the HPA)"
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.8.0/components.yaml
  kubectl patch deployment metrics-server -n kube-system --type=json \
    -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
fi

# ── Images ──────────────────────────────────────────────────────────────────
log "Building images (this takes a few minutes the first time — Chromium)"
docker build --target api   -t equitable-api:dev   "$REPO_ROOT/backend_ml"
docker build --target agent -t equitable-agent:dev "$REPO_ROOT/backend_ml"

# kind nodes are containers with their own image store; they cannot see the
# host daemon's images. Without this the pods sit in ErrImagePull.
log "Loading images into the kind cluster"
kind load docker-image equitable-api:dev   --name "$CLUSTER"
kind load docker-image equitable-agent:dev --name "$CLUSTER"

# ── Application ─────────────────────────────────────────────────────────────
log "Applying manifests"
kubectl apply -f "$REPO_ROOT/k8s/00-namespace.yaml"

# Built from .env at apply time so real credentials never touch a tracked file.
log "Creating Secret from $ENV_FILE"
kubectl create secret generic equitable-secrets \
  --namespace "$NAMESPACE" \
  --from-env-file="$ENV_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

# 11-secret.example.yaml is a committed placeholder template — applying it
# would overwrite the real Secret with REPLACE_ME values.
for f in 10-configmap 15-serviceaccounts 20-api-deployment 30-api-service \
         31-api-pdb 40-api-hpa 50-api-ingress 60-refresh-cronjob 70-networkpolicy; do
  kubectl apply -f "$REPO_ROOT/k8s/${f}.yaml"
done

log "Installing TLS certificate for the Ingress"
"$REPO_ROOT/scripts/k8s-tls-secret.sh"

log "Waiting for the API rollout"
kubectl rollout status deployment/equitable-api -n "$NAMESPACE" --timeout=300s

log "Done"
kubectl get pods,svc,ingress,hpa,cronjob -n "$NAMESPACE"
cat <<'EOF'

Try it:
  curl -k https://equitable.localtest.me/healthz/ready
  curl -k https://equitable.localtest.me/pantries | head -c 400

Trigger a refresh run immediately instead of waiting for the schedule:
  kubectl create job -n equitable --from=cronjob/equitable-refresh manual-$(date +%s)
EOF
