#!/usr/bin/env bash
set -Eeuo pipefail

: "${IMAGE:?IMAGE must be an immutable image digest}"
if [[ ! "$IMAGE" =~ @sha256:[0-9a-fA-F]{64}$ ]]; then
  echo "IMAGE must end in an immutable @sha256 digest." >&2
  exit 2
fi
namespace="${KUBE_NAMESPACE:-vglpos}"
migration_job="vglpos-migrate-$(date -u +%Y%m%d%H%M%S)"
smoke_port="${POST_DEPLOY_SMOKE_PORT:-18080}"
port_forward_log="$(mktemp)"
port_forward_pid=""
cleanup() {
  if [[ -n "$port_forward_pid" ]]; then
    kill "$port_forward_pid" >/dev/null 2>&1 || true
    wait "$port_forward_pid" >/dev/null 2>&1 || true
  fi
  rm -f -- "$port_forward_log"
}
trap cleanup EXIT

sed -e "s/name: vglpos-migrate/name: $migration_job/" \
  -e "s#ghcr.io/example/vglpos:replace-at-deploy#$IMAGE#" \
  ops/kubernetes/migration-job.yml | kubectl -n "$namespace" create -f -
kubectl -n "$namespace" wait --for=condition=complete "job/$migration_job" --timeout=10m

kubectl -n "$namespace" set image deployment/vglpos "app=$IMAGE" --record
kubectl -n "$namespace" rollout status deployment/vglpos --timeout=10m
kubectl -n "$namespace" port-forward service/vglpos "$smoke_port:80" >"$port_forward_log" 2>&1 &
port_forward_pid="$!"
smoke_ready=0
for _attempt in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:$smoke_port/ready" >/dev/null; then
    smoke_ready=1
    break
  fi
  sleep 1
done
if [[ "$smoke_ready" != "1" ]]; then
  cat "$port_forward_log" >&2
  exit 1
fi
curl --fail --silent "http://127.0.0.1:$smoke_port/health" >/dev/null
printf 'deployment=passed image=%s migration_job=%s\n' "$IMAGE" "$migration_job"
