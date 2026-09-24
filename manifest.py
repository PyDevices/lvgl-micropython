# Frozen Python helpers that ship with the LVGL MicroPython usermod.
# Source of truth: PyDevices/lvgl-bindings python/ (display_driver.py, fs_driver.py)
# Sync: ./scripts/sync_from_lvgl_bindings.sh
#
# This file only freezes usermod helpers and names the C module. Upstream
# port/board/variant frozen modules come from your own manifest, which pulls
# this one in with include("<path to lvgl-micropython>/manifest.py").

module("display_driver.py", base_path="./lib", opt=3)
module("fs_driver.py", base_path="./lib", opt=3)

# MicroPython 1.29: the manifest names its own C module.
c_module(".")  # this directory holds the micropython.cmake / micropython.mk for the C half
