#!/usr/bin/env bash
# Sync the hand-written Python helpers (display_driver.py, fs_driver.py)
# from PyDevices/lvgl-bindings on GitHub (not the local workspace).
#
# Usage:
#   ./scripts/sync_from_lvgl_bindings.sh --ref <40-character commit SHA>
#   ./scripts/sync_from_lvgl_bindings.sh --ref v9.5.N
#
# After syncing, commit the updated files under lib/ in this repo.

set -euo pipefail

LV_BINDINGS_REPO="${LV_BINDINGS_REPO:-https://github.com/PyDevices/lvgl-bindings.git}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"

REF="${LV_BINDINGS_REF:-}"
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

if [[ -z "$REF" ]]; then
    REF=$(tr -d '[:space:]' < "$SOURCE_REPO/LVGL_BINDINGS_COMMIT")
fi
if [[ ! "$REF" =~ ^[0-9a-fA-F]{40}$ && ! "$REF" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: --ref must be an exact 40-character commit SHA or vX.Y.Z tag, got: $REF" >&2
    exit 1
fi

TMP=$(mktemp -d)
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

HELPERS=(display_driver.py fs_driver.py)

echo "Fetching ${LV_BINDINGS_REPO} @ ${REF}..."
git clone --filter=blob:none --no-checkout "${LV_BINDINGS_REPO}" "${TMP}/lvgl-bindings"
git -C "${TMP}/lvgl-bindings" fetch origin "$REF"
RESOLVED_REF=$(git -C "${TMP}/lvgl-bindings" rev-parse 'FETCH_HEAD^{commit}')
for helper in "${HELPERS[@]}"; do
    git -C "${TMP}/lvgl-bindings" checkout "$RESOLVED_REF" -- "python/${helper}"
done

mkdir -p "${SOURCE_REPO}/lib"
for helper in "${HELPERS[@]}"; do
    SRC="${TMP}/lvgl-bindings/python/${helper}"
    if [[ ! -f "$SRC" ]]; then
        echo "Error: python/${helper} not found on ${REF}." >&2
        exit 1
    fi
    cp "$SRC" "${SOURCE_REPO}/lib/${helper}"
done
printf '%s\n' "$RESOLVED_REF" > "${SOURCE_REPO}/LVGL_BINDINGS_COMMIT"

echo
echo "Synced from lvgl-bindings ${RESOLVED_REF}:"
for helper in "${HELPERS[@]}"; do
    echo "  lib/${helper}"
done
echo
echo "Commit when ready:"
echo "  LVGL_BINDINGS_COMMIT"
echo "  git add LVGL_BINDINGS_COMMIT lib/"
echo "  git commit -m \"Sync Python helpers from lvgl-bindings ${RESOLVED_REF}.\""
