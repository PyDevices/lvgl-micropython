#!/usr/bin/env bash
# Fetch lvgl-bindings at the commit in LVGL_BINDINGS_COMMIT into
# .deps/lvgl-bindings, with only what this module compiles: generated/,
# lv_conf.h, and LVGL's src/ plus its top-level headers. Shallow, sparse and
# blobless, so it downloads tens of MB rather than LVGL's whole history.
#
# The build runs this itself when there is no BINDINGS_DIR and no
# lvgl-bindings checkout beside this one (a clone outside the PyDevices
# workspace); in the workspace the sibling wins and this never runs.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST="$HERE/.deps/lvgl-bindings"
URL="${LV_BINDINGS_REPO:-https://github.com/PyDevices/lvgl-bindings.git}"
PIN=$(tr -d '[:space:]' < "$HERE/LVGL_BINDINGS_COMMIT")

if [[ -d "$DEST/.git" && "$(git -C "$DEST" rev-parse HEAD 2>/dev/null)" == "$PIN" && -f "$DEST/lvgl/lvgl.h" ]]; then
    echo "lvgl-bindings ${PIN:0:12} already in .deps"
    exit 0
fi
rm -rf "$DEST"
mkdir -p "$DEST"
git -C "$DEST" init -q
git -C "$DEST" remote add origin "$URL"
git -C "$DEST" config extensions.partialClone origin
git -C "$DEST" sparse-checkout set generated lvgl
git -C "$DEST" fetch -q --depth 1 --filter=blob:none origin "$PIN"
git -C "$DEST" checkout -q FETCH_HEAD
# LVGL itself, as its own partial clone at the commit lvgl-bindings records:
# `git submodule update` ignores --filter and pulls a ~100 MB pack.
LVGL_SHA=$(git -C "$DEST" ls-tree HEAD lvgl | awk '{print $3}')
LVGL_URL=$(git -C "$DEST" config -f .gitmodules submodule.lvgl.url)
rm -rf "$DEST/lvgl"
mkdir -p "$DEST/lvgl"
git -C "$DEST/lvgl" init -q
git -C "$DEST/lvgl" remote add origin "$LVGL_URL"
git -C "$DEST/lvgl" config extensions.partialClone origin
git -C "$DEST/lvgl" sparse-checkout set src
git -C "$DEST/lvgl" fetch -q --depth 1 --filter=blob:none origin "$LVGL_SHA"
git -C "$DEST/lvgl" checkout -q FETCH_HEAD
echo "lvgl-bindings ${PIN:0:12} fetched into $DEST"
