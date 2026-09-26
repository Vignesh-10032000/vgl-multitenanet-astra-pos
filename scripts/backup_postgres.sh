#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_DATABASE_URL:?BACKUP_DATABASE_URL is required}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT is required}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
dump="$work_dir/vglpos-$timestamp.dump"
manifest="$work_dir/vglpos-$timestamp.manifest.json"

pg_dump --dbname="$BACKUP_DATABASE_URL" --format=custom --no-owner --no-acl --file="$dump"
psql "$BACKUP_DATABASE_URL" --no-psqlrc --tuples-only --no-align \
  --file="scripts/backup_manifest.sql" > "$manifest"
age --recipient "$AGE_RECIPIENT" --output "$dump.age" "$dump"
age --recipient "$AGE_RECIPIENT" --output "$manifest.age" "$manifest"

if [[ -n "${BACKUP_OUTPUT_DIR:-}" ]]; then
  mkdir -p -- "$BACKUP_OUTPUT_DIR"
  install -m 0600 "$dump.age" "$manifest.age" "$BACKUP_OUTPUT_DIR/"
else
  : "${BACKUP_BUCKET:?BACKUP_BUCKET is required when BACKUP_OUTPUT_DIR is unset}"
  aws s3 cp "$dump.age" "s3://$BACKUP_BUCKET/nightly/$(basename "$dump.age")" --only-show-errors
  aws s3 cp "$manifest.age" "s3://$BACKUP_BUCKET/nightly/$(basename "$manifest.age")" --only-show-errors
  if [[ "$(date -u +%d)" == "01" ]]; then
    aws s3 cp "$dump.age" "s3://$BACKUP_BUCKET/monthly/$(basename "$dump.age")" --only-show-errors
    aws s3 cp "$manifest.age" "s3://$BACKUP_BUCKET/monthly/$(basename "$manifest.age")" --only-show-errors
  fi
fi

if [[ -n "${BACKUP_METRICS_FILE:-}" ]]; then
  metrics_dir="$(dirname "$BACKUP_METRICS_FILE")"
  mkdir -p -- "$metrics_dir"
  printf 'vglpos_backup_last_success_timestamp_seconds %s\n' "$(date -u +%s)" > "$BACKUP_METRICS_FILE"
fi
printf 'backup=%s rpo_target_minutes=15\n' "$(basename "$dump.age")"
