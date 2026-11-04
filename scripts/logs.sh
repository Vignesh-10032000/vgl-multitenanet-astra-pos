#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -eq 0 ]]; then
  exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$script_dir/android-emulator.ps1")" -Action logs
elif [[ $# -eq 1 && "$1" == '--dump' ]]; then
  exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$script_dir/android-emulator.ps1")" -Action logs -Dump
else
  printf 'Usage: %s [--dump]\n' "$0" >&2
  exit 2
fi
