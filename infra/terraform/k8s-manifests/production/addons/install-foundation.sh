#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTEXT="${KUBE_CONTEXT:-ctdl-xtra-prod}"

CERT_MANAGER_VERSION="v1.17.1"
EXTERNAL_SECRETS_VERSION="2.4.1"
INGRESS_NGINX_VERSION="4.12.1"
METRICS_SERVER_VERSION="3.12.2"

kubectl --context "${CONTEXT}" apply -f "${ROOT_DIR}/cluster/namespace.yaml"
kubectl --context "${CONTEXT}" apply -f "${ROOT_DIR}/cluster/storageclass-gp3.yaml"

helm repo add jetstack https://charts.jetstack.io --force-update
helm repo add external-secrets https://charts.external-secrets.io --force-update
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx --force-update
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ --force-update
helm repo update

helm upgrade --install cert-manager jetstack/cert-manager \
  --kube-context "${CONTEXT}" \
  --namespace cert-manager \
  --create-namespace \
  --version "${CERT_MANAGER_VERSION}" \
  --set installCRDs=true \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="arn:aws:iam::996810415034:role/ctdl-xtra-prod-cert-manager-irsa-role" \
  --wait \
  --timeout 5m

kubectl --context "${CONTEXT}" apply -f "${ROOT_DIR}/cluster/cert-manager-cluster-issuer.yaml"

helm upgrade --install external-secrets external-secrets/external-secrets \
  --kube-context "${CONTEXT}" \
  --namespace external-secrets \
  --create-namespace \
  --version "${EXTERNAL_SECRETS_VERSION}" \
  --values "${SCRIPT_DIR}/external-secrets-values.yaml" \
  --wait \
  --timeout 5m

kubectl --context "${CONTEXT}" apply -f "${ROOT_DIR}/cluster/cluster-secret-store.yaml"

helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --kube-context "${CONTEXT}" \
  --namespace ingress-nginx \
  --create-namespace \
  --version "${INGRESS_NGINX_VERSION}" \
  --values "${SCRIPT_DIR}/ingress-nginx-values.yaml" \
  --wait \
  --timeout 10m

helm upgrade --install metrics-server metrics-server/metrics-server \
  --kube-context "${CONTEXT}" \
  --namespace kube-system \
  --version "${METRICS_SERVER_VERSION}" \
  --values "${SCRIPT_DIR}/metrics-server-values.yaml" \
  --wait \
  --timeout 5m

kubectl --context "${CONTEXT}" apply -f "${SCRIPT_DIR}/cluster-autoscaler.yaml"
kubectl --context "${CONTEXT}" -n kube-system rollout status deployment/cluster-autoscaler --timeout=180s
