# Frozen Python helpers that ship with the LVGL MicroPython usermod.
# Source of truth: PyDevices/lvgl-bindings python/display_driver.py
# Sync: ./scripts/sync_from_lvgl_bindings.sh
#
# This file only freezes usermod helpers. Upstream port/board/variant frozen
# modules come from a workspace aggregator manifest or from
# FROZEN_MANIFEST_UPSTREAM when you wrap this file yourself.

module("display_driver.py", base_path="./lib", opt=3)
