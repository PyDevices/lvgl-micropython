# lvgl-micropython

MicroPython user C module glue for LVGL: `micropython.mk`, CMake usermod, GC-aware allocator, and smoke tests.

This repo is a consumer/build repo for the LVGL stack. It consumes generated bindings from lvgl-bindings and rebuilds MicroPython targets, but it does not publish its own package to TestPyPI; lvgl-python is the publishing endpoint for the family.

Requires a sibling clone of [lvgl-bindings](https://github.com/PyDevices/lvgl-bindings) with `generated/lvgl_micropython.c` (run `regenerate_lvmp.sh`).

## Documentation

See [docs/](docs/index.md).

This repo is mostly glue: it wires LVGL into MicroPython builds and exposes the runtime hooks that the firmware needs. In practice, you usually change the build glue or allocator here when the port itself changes, but you do not regenerate the bindings here. If the binding layer changed, update **`lvgl-bindings`** first and then rebuild this module against the new generated file.

## Workspace layout

```
workspace/
  lvgl-micropython/     ← this repo
  lvgl-bindings/
  micropython/             ← for builds
```

## Generate bindings

```bash
cd lvgl-bindings
git submodule update --init lvgl
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./regenerate_lvmp.sh
```

## Build (Make ports)

`USER_C_MODULES` is the **workspace parent** (directory containing this repo and any other `*/micropython.mk` siblings):

```bash
cd micropython/ports/unix
# Optional: freeze display_driver.py from this repo. To also keep the port's
# default frozen modules, write a small wrapper that include()s this manifest
# and the port/variant manifest.py.
make USER_C_MODULES=../../.. FROZEN_MANIFEST=../../../lvgl-micropython/manifest.py
```

Override bindings location if needed:

```bash
make USER_C_MODULES=../../.. BINDINGS_DIR=/path/to/lvgl-bindings
```

## Build (CMake ports)

`USER_C_MODULES` points at **this repo** (or `lvgl-micropython/micropython.cmake`). CMake does not scan the workspace for siblings:

```bash
cd micropython/ports/esp32
make BOARD=ESP32_GENERIC_S3 USER_C_MODULES=../../../lvgl-micropython

cd micropython/ports/rp2
make BOARD=RPI_PICO USER_C_MODULES=../../../lvgl-micropython
```

To include this module **plus** other usermods, pass a semicolon-separated list (no aggregator file required):

```bash
make BOARD=ESP32_GENERIC_S3 \
  USER_C_MODULES="/abs/path/to/lvgl-micropython;/abs/path/to/displayif"
```

See the [cmods workspace](https://github.com/PyDevices/cmods) for an easier way to build this repo with other user C modules.

## Smoke test

```bash
./micropython/ports/unix/build-standard/micropython ./lvgl-micropython/tools/test_lvgl_unix.py
```

Prefer the unified smoke test directly: `lvgl-bindings/tools/test_lvgl_smoke.py`.

## Files

| Path | Role |
|------|------|
| `micropython.mk` | Make ports — `USER_C_MODULES` = workspace parent |
| `micropython.cmake` | CMake ports — `USER_C_MODULES` = this repo (see above) |
| `src/lv_mem_core_micropython.c` | GC-aware LVGL allocator |
| `manifest.py` | Freezes `lib/display_driver.py` (sync from lvgl-bindings) |
| `lib/display_driver.py` | Vendored pydisplay LVGL glue (`import display_driver`) |
| `scripts/sync_from_lvgl_bindings.sh` | Refresh `lib/display_driver.py` from lvgl-bindings |
| `tools/test_lvgl_unix.py` | Deprecated wrapper → `lvgl-bindings/tools/test_lvgl_smoke.py` |

CircuitPython integration lives in [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython).
