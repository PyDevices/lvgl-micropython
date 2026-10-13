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
| `LVGL_BINDINGS_COMMIT` | The lvgl-bindings commit a build fetches when it has no checkout to use |

## Build

`USER_C_MODULES` is the **workspace parent** (directory containing this repo):

```bash
cd micropython/ports/unix
make USER_C_MODULES=../../.. FROZEN_MANIFEST=../../../lvgl-micropython/manifest.py
```

CMake ports (esp32, rp2): point `USER_C_MODULES` at **this repo**.

The bindings come from `BINDINGS_DIR` if you set it, else an `lvgl-bindings`
checkout beside this repo, else the commit in `LVGL_BINDINGS_COMMIT`, fetched
into `.deps/`. A checkout you supply is built as it is, with a note when it
differs from the pin; see the [README](../README.md#build).

On MicroPython 1.29+, `manifest.py` names the C module itself via `c_module()`, so adding `include("<path to lvgl-micropython>/manifest.py")` to your own manifest builds it alongside other user C modules.

Sync only from an immutable source:

```bash
./scripts/sync_from_lvgl_bindings.sh --ref <40-character-commit-sha>
# or: --ref v9.5.N
```

## Smoke (developer)

```bash
./micropython/ports/unix/build-standard/micropython \
  ./lvgl-bindings/tools/test_lvgl_smoke.py
```

## Related

- CircuitPython: [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython)
- CPython: [lvgl-python](https://github.com/PyDevices/lvgl-python) (`pip install pydevices-lvgl`)
