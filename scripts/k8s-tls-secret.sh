#!/usr/bin/env bash
# Generate a self-signed TLS cert for the local Ingress host and load it into
# the cluster as the secret the Ingress references.
#
# Local only. On a real cluster, cert-manager issues a trusted cert into this
# same secret name, so no manifest changes are needed — only this script goes
# away.
set -euo pipefail

HOST="${1:-equitable.localtest.me}"
NAMESPACE="${NAMESPACE:-equitable}"
SECRET="${SECRET:-equitable-api-tls}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# -addext subjectAltName is required: browsers and Go's TLS stack have ignored
# the CN field for hostname verification for years, so a cert with only a CN
# fails verification even though it looks correct.
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "$WORKDIR/tls.key" \
  -out "$WORKDIR/tls.crt" \
  -days 365 \
  -subj "/CN=${HOST}/O=EquiTable Local" \
  -addext "subjectAltName=DNS:${HOST}" \
  2>/dev/null

# --dry-run=client | apply makes this idempotent: re-running rotates the cert
# instead of failing with AlreadyExists.
kubectl create secret tls "$SECRET" \
  --namespace "$NAMESPACE" \
  --cert="$WORKDIR/tls.crt" \
  --key="$WORKDIR/tls.key" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "TLS secret '${SECRET}' installed in namespace '${NAMESPACE}' for host ${HOST}"
echo "Self-signed: curl needs -k, and a browser will warn. That is expected locally."
