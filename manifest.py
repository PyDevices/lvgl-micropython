# Frozen Python helpers that ship with the LVGL MicroPython usermod.
# Source of truth: PyDevices/lvgl-bindings python/ (display_driver.py, fs_driver.py)
# Sync: ./scripts/sync_from_lvgl_bindings.sh
#
# This file only freezes usermod helpers. Upstream port/board/variant frozen
# modules come from a workspace aggregator manifest or from
# FROZEN_MANIFEST_UPSTREAM when you wrap this file yourself.

module("display_driver.py", base_path="./lib", opt=3)
module("fs_driver.py", base_path="./lib", opt=3)

# MicroPython 1.29: the manifest names its own C module (workspace retool, piece 1).
c_module(".")  # this directory holds the micropython.cmake / micropython.mk for the C half
