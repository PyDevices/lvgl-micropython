# lvgl-micropython

MicroPython **user C module** glue for [LVGL](https://lvgl.io/): Make/CMake
usermod entry points, a GC-aware allocator, and an optional frozen manifest.

This repo does **not** regenerate bindings. It consumes
[`lvgl-bindings`](https://github.com/PyDevices/lvgl-bindings)
(`generated/lvgl_micropython.c` + the `lvgl` submodule).

## Layout

| Path | Role |
|------|------|
| `micropython.mk` / `micropython.cmake` | Build glue (`USER_C_MODULES`) |
| `src/lv_mem_core_micropython.c` | GC-aware LVGL allocator |
| `manifest.py` | Optional frozen Python modules |
| `docs/` | This documentation |
| `tools/test_lvgl_unix.py` | Deprecated smoke wrapper → `lvgl-bindings/tools/test_lvgl_smoke.py` |

## Build

`USER_C_MODULES` is the **workspace parent** (directory containing this repo):

```bash
cd micropython/ports/unix
make USER_C_MODULES=../../.. FROZEN_MANIFEST=../../../lvgl-micropython/manifest.py
```

CMake ports (esp32, rp2): point `USER_C_MODULES` at **this repo**.

See the [cmods workspace](https://github.com/PyDevices/cmods) for an easier way to build this repo with other user C modules.

## Smoke (developer)

```bash
./micropython/ports/unix/build-standard/micropython \
  ./lvgl-bindings/tools/test_lvgl_smoke.py
```

## Related

- CircuitPython: [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython)
- CPython: [lvgl-python](https://github.com/PyDevices/lvgl-python) (`pip install pydevices-lvgl`)
