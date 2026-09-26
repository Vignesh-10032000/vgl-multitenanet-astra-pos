#!/usr/bin/env bash
set -Eeuo pipefail

: "${WAL_BUCKET:?WAL_BUCKET is required}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT is required}"
source_path="${1:?WAL source path is required}"
wal_name="${2:?WAL file name is required}"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
encrypted="$work_dir/$wal_name.age"
age --recipient "$AGE_RECIPIENT" --output "$encrypted" "$source_path"
aws s3 cp "$encrypted" "s3://$WAL_BUCKET/wal/$wal_name.age" --only-show-errors
