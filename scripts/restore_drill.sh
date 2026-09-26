#!/usr/bin/env bash
set -Eeuo pipefail

: "${DRILL_ADMIN_URL:?DRILL_ADMIN_URL is required (maintenance database URL)}"
: "${AGE_IDENTITY_FILE:?AGE_IDENTITY_FILE is required}"

if [[ ! -f "$AGE_IDENTITY_FILE" ]]; then
  echo "AGE_IDENTITY_FILE does not exist" >&2
  exit 2
fi
if [[ -n "${BACKUP_OUTPUT_DIR:-}" ]]; then
  identity_real="$(realpath "$AGE_IDENTITY_FILE")"
  backup_real="$(realpath "$BACKUP_OUTPUT_DIR")"
  if [[ "$identity_real" == "$backup_real"/* ]]; then
    echo "Encryption identity must not be stored alongside backups" >&2
    exit 2
  fi
fi

started="$(date -u +%s)"
scratch="vglpos_restore_drill_${started}_$$"
work_dir="$(mktemp -d)"
cleanup() {
  dropdb --if-exists --force --maintenance-db="$DRILL_ADMIN_URL" "$scratch" >/dev/null 2>&1 || true
  rm -rf -- "$work_dir"
}
trap cleanup EXIT

if [[ -n "${BACKUP_OUTPUT_DIR:-}" ]]; then
  encrypted_dump="$(find "$BACKUP_OUTPUT_DIR" -maxdepth 1 -type f -name 'vglpos-*.dump.age' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
  [[ -n "$encrypted_dump" ]] || { echo "No encrypted backup found" >&2; exit 3; }
  encrypted_manifest="${encrypted_dump%.dump.age}.manifest.json.age"
else
  : "${BACKUP_BUCKET:?BACKUP_BUCKET is required when BACKUP_OUTPUT_DIR is unset}"
  latest_key="$(aws s3api list-objects-v2 --bucket "$BACKUP_BUCKET" --prefix nightly/ --query 'reverse(sort_by(Contents[?ends_with(Key, `.dump.age`)], &LastModified))[0].Key' --output text)"
  [[ "$latest_key" != "None" ]] || { echo "No encrypted backup found" >&2; exit 3; }
  encrypted_dump="$work_dir/backup.dump.age"
  encrypted_manifest="$work_dir/backup.manifest.json.age"
  aws s3 cp "s3://$BACKUP_BUCKET/$latest_key" "$encrypted_dump" --only-show-errors
  aws s3 cp "s3://$BACKUP_BUCKET/${latest_key%.dump.age}.manifest.json.age" "$encrypted_manifest" --only-show-errors
fi

age --decrypt --identity "$AGE_IDENTITY_FILE" --output "$work_dir/backup.dump" "$encrypted_dump"
age --decrypt --identity "$AGE_IDENTITY_FILE" --output "$work_dir/expected.json" "$encrypted_manifest"
createdb --maintenance-db="$DRILL_ADMIN_URL" "$scratch"
scratch_url="${DRILL_ADMIN_URL%/*}/$scratch"
pg_restore --dbname="$scratch_url" --no-owner --no-acl --exit-on-error "$work_dir/backup.dump"
actual="$(psql "$scratch_url" --no-psqlrc --tuples-only --no-align --file=scripts/restore_integrity.sql | head -1)"
expected="$(tr -d '\r\n' < "$work_dir/expected.json")"
if [[ "$actual" != "$expected" ]]; then
  echo "Integrity totals differ: expected=$expected actual=$actual" >&2
  exit 4
fi

elapsed="$(( $(date -u +%s) - started ))"
if (( elapsed > 3600 )); then
  echo "Restore exceeded RTO: ${elapsed}s > 3600s" >&2
  exit 5
fi
printf 'restore_drill=passed database=%s rpo_target_minutes=15 rto_seconds=%s rto_target_seconds=3600\n' "$scratch" "$elapsed"
