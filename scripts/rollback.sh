#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${CONFIRM_ROLLBACK:-}" != "yes" ]]; then
  echo "Set CONFIRM_ROLLBACK=yes after incident-command approval." >&2
  exit 2
fi
: "${PREVIOUS_IMAGE:?PREVIOUS_IMAGE must be the last known-good immutable digest}"
if [[ ! "$PREVIOUS_IMAGE" =~ @sha256:[0-9a-fA-F]{64}$ ]]; then
  echo "PREVIOUS_IMAGE must end in an immutable @sha256 digest." >&2
  exit 2
fi
namespace="${KUBE_NAMESPACE:-vglpos}"

# Database rollback is a deliberate, separate release action. Run only when
# the release notes certify that downgrade -1 is data-safe.
if [[ "${ROLLBACK_DATABASE:-no}" == "yes" ]]; then
  job="vglpos-downgrade-$(date -u +%Y%m%d%H%M%S)"
  sed -e "s/name: vglpos-migrate/name: $job/" \
    -e "s#ghcr.io/example/vglpos:replace-at-deploy#$PREVIOUS_IMAGE#" \
    -e 's/\["alembic", "upgrade", "head"\]/["alembic", "downgrade", "-1"]/' \
    ops/kubernetes/migration-job.yml | kubectl -n "$namespace" create -f -
  kubectl -n "$namespace" wait --for=condition=complete "job/$job" --timeout=10m
fi

kubectl -n "$namespace" set image deployment/vglpos "app=$PREVIOUS_IMAGE"
kubectl -n "$namespace" rollout status deployment/vglpos --timeout=10m
printf 'rollback=passed image=%s database_downgraded=%s\n' "$PREVIOUS_IMAGE" "${ROLLBACK_DATABASE:-no}"
