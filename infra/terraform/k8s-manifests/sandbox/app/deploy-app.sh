#!/usr/bin/env bash
set -euo pipefail

: "${IMAGE_TAG:?IMAGE_TAG must be set (e.g. sha-abc1234)}"
: "${EFS_FS_ID:?EFS_FS_ID must be set (terraform output efs_file_system_id)}"
export IMAGE_TAG EFS_FS_ID

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTEXT="${KUBE_CONTEXT:-ctdl-xtra-sandbox}"
NAMESPACE="ctdl-xtra"
TMP_DIR="$(mktemp -d)"

trap 'rm -rf "${TMP_DIR}"' EXIT

kubectl --context "${CONTEXT}" apply -f "${SCRIPT_DIR}/externalsecret.yaml"
envsubst '${EFS_FS_ID}' < "${SCRIPT_DIR}/storage.yaml" | kubectl --context "${CONTEXT}" apply -f -
curl -fsSL "https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem" -o "${TMP_DIR}/rds-global-bundle.pem"
kubectl --context "${CONTEXT}" -n "${NAMESPACE}" create configmap rds-ca-bundle \
  --from-file="rds-global-bundle.pem=${TMP_DIR}/rds-global-bundle.pem" \
  --dry-run=client \
  -o yaml | kubectl --context "${CONTEXT}" apply -f -
kubectl --context "${CONTEXT}" -n "${NAMESPACE}" wait --for=condition=Ready externalsecret/ctdl-xtra-app --timeout=120s
kubectl --context "${CONTEXT}" -n "${NAMESPACE}" delete job ctdl-xtra-db-migrate --ignore-not-found
envsubst '${IMAGE_TAG}' < "${SCRIPT_DIR}/db-migrate-job.yaml" | kubectl --context "${CONTEXT}" apply -f -
kubectl --context "${CONTEXT}" -n "${NAMESPACE}" wait --for=condition=Complete job/ctdl-xtra-db-migrate --timeout=300s
kubectl --context "${CONTEXT}" apply -f "${SCRIPT_DIR}/redis-configmap.yaml"
kubectl --context "${CONTEXT}" apply -f "${SCRIPT_DIR}/redis-externalsecret.yaml"
kubectl --context "${CONTEXT}" apply -f "${SCRIPT_DIR}/redis-statefulset.yaml"
kubectl --context "${CONTEXT}" apply -f "${SCRIPT_DIR}/service.yaml"
envsubst '${IMAGE_TAG}' < "${SCRIPT_DIR}/deployment.yaml" | kubectl --context "${CONTEXT}" apply -f -
kubectl --context "${CONTEXT}" apply -f "${SCRIPT_DIR}/ingress.yaml"
kubectl --context "${CONTEXT}" -n "${NAMESPACE}" rollout status deployment/ctdl-xtra-api --timeout=300s
kubectl --context "${CONTEXT}" -n "${NAMESPACE}" rollout status deployment/ctdl-xtra-worker --timeout=300s
