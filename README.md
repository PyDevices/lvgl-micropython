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

Or clone into [cmods](https://github.com/PyDevices/cmods) when using the optional MP wrapper.

## Generate bindings

```bash
cd lv_bindings
git submodule update --init lvgl
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./regenerate_lvmp.sh
```

## Build (direct)

From a MicroPython port directory, set `USER_C_MODULES` to the **workspace root** (parent of this repo):

```bash
cd micropython/ports/unix
make USER_C_MODULES=../../.. FROZEN_MANIFEST=../../../lv_micropython_cmod/manifest.py
```

Override bindings location if needed:

```bash
make USER_C_MODULES=../../.. BINDINGS_DIR=/path/to/lv_bindings
```

## Build (cmods wrapper)

```bash
git clone https://github.com/PyDevices/cmods.git
cd cmods
git clone https://github.com/micropython/micropython.git micropython
git clone https://github.com/PyDevices/lv_micropython_cmod.git lv_micropython_cmod
git clone https://github.com/PyDevices/lv_bindings.git lv_bindings
cd micropython && git submodule update --init --recursive && cd ..
./lv_bindings/regenerate_lvmp.sh
./build_unix.sh
```

## Smoke test

```bash
./micropython/ports/unix/build-standard/micropython ./lv_micropython_cmod/test_lvgl_unix.py
```

## Files

| Path | Role |
|------|------|
| `micropython.mk` | Unix/Make ports |
| `micropython.cmake` | ESP32/RP2 CMake ports (via cmods `micropython.cmake`) |
| `lv_mem_core_micropython.c` | GC-aware LVGL allocator |
| `manifest.py` | Optional frozen Python modules |
| `test_lvgl_unix.py` | Headless unix smoke test |

CircuitPython integration lives in [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod).
