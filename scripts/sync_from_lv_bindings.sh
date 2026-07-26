#!/usr/bin/env bash
# Sync python/display_driver.py from PyDevices/lv_bindings on GitHub
# (not the local workspace).
#
# Usage:
#   ./scripts/sync_from_lv_bindings.sh
#   ./scripts/sync_from_lv_bindings.sh --ref abc1234
#   LV_BINDINGS_REF=main ./scripts/sync_from_lv_bindings.sh
#
# After syncing, commit the updated lib/display_driver.py in this repo.

set -euo pipefail

LV_BINDINGS_REPO="${LV_BINDINGS_REPO:-https://github.com/PyDevices/lv_bindings.git}"
LV_BINDINGS_REF="${LV_BINDINGS_REF:-main}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"

REF="$LV_BINDINGS_REF"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ref)
            REF=$2
            shift 2
            ;;
        --help | -h)
            sed -n '2,12p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

TMP=$(mktemp -d)
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "Fetching ${LV_BINDINGS_REPO} @ ${REF}..."
git clone --filter=blob:none --no-checkout "${LV_BINDINGS_REPO}" "${TMP}/lv_bindings"
git -C "${TMP}/lv_bindings" checkout "${REF}" -- python/display_driver.py

SRC="${TMP}/lv_bindings/python/display_driver.py"
if [[ ! -f "$SRC" ]]; then
    echo "Error: python/display_driver.py not found on ${REF}." >&2
    exit 1
fi

mkdir -p "${SOURCE_REPO}/lib"
cp "$SRC" "${SOURCE_REPO}/lib/display_driver.py"

echo
echo "Synced from lv_bindings ${REF}:"
echo "  lib/display_driver.py"
echo
echo "Commit when ready:"
echo "  git add lib/display_driver.py"
echo "  git commit -m \"Sync display_driver.py from lv_bindings ${REF}.\""
