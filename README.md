# lv_micropython_cmod

MicroPython user C module glue for LVGL: `micropython.mk`, CMake usermod, GC-aware allocator, and smoke tests.

Requires a sibling clone of [lv_bindings](https://github.com/PyDevices/lv_bindings) with `generated/lvgl_micropython.c` (run `regenerate_lvmp.sh`).

## Workspace layout

```
workspace/
  lv_micropython_cmod/     ← this repo
  lv_bindings/
  micropython/             ← for builds
```

## Generate bindings

```bash
cd lv_bindings
git submodule update --init lvgl
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./regenerate_lvmp.sh
```

## Build (Make ports)

`USER_C_MODULES` is the **workspace parent** (directory containing this repo and any other `*/micropython.mk` siblings):

```bash
cd micropython/ports/unix
make USER_C_MODULES=../../.. FROZEN_MANIFEST=../../../lv_micropython_cmod/manifest.py
```

Override bindings location if needed:

```bash
make USER_C_MODULES=../../.. BINDINGS_DIR=/path/to/lv_bindings
```

## Build (CMake ports)

`USER_C_MODULES` points at **this repo** (or `lv_micropython_cmod/micropython.cmake`). CMake does not scan the workspace for siblings:

```bash
cd micropython/ports/esp32
make BOARD=ESP32_GENERIC_S3 USER_C_MODULES=../../../lv_micropython_cmod

cd micropython/ports/rp2
make BOARD=RPI_PICO USER_C_MODULES=../../../lv_micropython_cmod
```

To include this module **plus** other usermods, pass a semicolon-separated list (no aggregator file required):

```bash
make BOARD=ESP32_GENERIC_S3 \
  USER_C_MODULES="/abs/path/to/lv_micropython_cmod;/abs/path/to/displayif"
```

([cmods](https://github.com/PyDevices/cmods) is an optional convenience workspace with `./build_mp.sh`; it is not required.)

## Smoke test

```bash
./micropython/ports/unix/build-standard/micropython ./lv_micropython_cmod/test_lvgl_unix.py
```

## Files

| Path | Role |
|------|------|
| `micropython.mk` | Make ports — `USER_C_MODULES` = workspace parent |
| `micropython.cmake` | CMake ports — `USER_C_MODULES` = this repo (see above) |
| `lv_mem_core_micropython.c` | GC-aware LVGL allocator |
| `manifest.py` | Optional frozen Python modules |
| `test_lvgl_unix.py` | Headless unix smoke test |

CircuitPython integration lives in [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod).
