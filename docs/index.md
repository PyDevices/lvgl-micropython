# lv_micropython_cmod

MicroPython **user C module** glue for [LVGL](https://lvgl.io/): Make/CMake
usermod entry points, a GC-aware allocator, and an optional frozen manifest.

This repo does **not** regenerate bindings. It consumes
[`lv_bindings`](https://github.com/PyDevices/lv_bindings)
(`generated/lvgl_micropython.c` + the `lvgl` submodule).

## Layout

| Path | Role |
|------|------|
| `micropython.mk` / `micropython.cmake` | Build glue (`USER_C_MODULES`) |
| `src/lv_mem_core_micropython.c` | GC-aware LVGL allocator |
| `manifest.py` | Optional frozen Python modules |
| `docs/` | This documentation |
| `tools/test_lvgl_unix.py` | Deprecated smoke wrapper → `lv_bindings/tools/test_lvgl_smoke.py` |

## Build

`USER_C_MODULES` is the **workspace parent** (directory containing this repo):

```bash
cd micropython/ports/unix
make USER_C_MODULES=../../.. FROZEN_MANIFEST=../../../lv_micropython_cmod/manifest.py
```

Or use [cmods](https://github.com/PyDevices/cmods) `./build_mp.sh` / `./build_target.sh mp-unix`.

CMake ports (esp32, rp2): point `USER_C_MODULES` at **this repo**.

## Smoke (developer)

```bash
./micropython/ports/unix/build-standard/micropython \
  ./lv_bindings/tools/test_lvgl_smoke.py
```

## Related

- CircuitPython: [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod)
- CPython: [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod) (`pip install lvgl-cpython`)
