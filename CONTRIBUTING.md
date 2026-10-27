# Contributing to lvgl-micropython

This repository is build glue. It doesn't generate the bindings, and it
publishes no package. Change binding generation and the synced helper sources in
[lvgl-bindings](https://github.com/PyDevices/lvgl-bindings), then regenerate and
sync. Change this repository for MicroPython build integration, allocator
behavior or interpreter lifecycle. How to use the module is in the
[docs site](https://github.com/PyDevices/lvgl-bindings/blob/main/docs/index.md), built from lvgl-bindings.

A good first contribution is a focused integration or finalizer test, a fix to
the build documentation, or a change backed by the pinned binding smoke suite.
Run the smoke test from the exact pinned lvgl-bindings checkout, not from a copy
here.

## Where things are

| Path | What it is |
|---|---|
| `micropython.mk` | Make-port user-module entry point (before 1.29, `USER_C_MODULES` is the parent directory) |
| `micropython.cmake` | CMake-port entry point (before 1.29, `USER_C_MODULES` is this repository) |
| `manifest.py` | Names the C module with `c_module(".")` and freezes [`lib/fs_driver.py`](lib/fs_driver.py) |
| [`src/lv_mem_core_micropython.c`](src/lv_mem_core_micropython.c) | The GC-aware LVGL allocator |
| [`src/lvgl_micropython_build.c`](src/lvgl_micropython_build.c) | `lvgl_micropython.__revision__`, the build stamp |
| `lib/fs_driver.py` | LVGL filesystem driver, synced from lvgl-bindings |
| `LVGL_BINDINGS_COMMIT` | The lvgl-bindings commit a build fetches when it has no checkout to use |
| [`scripts/fetch_bindings.sh`](scripts/fetch_bindings.sh) | Fetches that commit into `.deps/` (the build runs it) |
| [`scripts/sync_from_lvgl_bindings.sh`](scripts/sync_from_lvgl_bindings.sh) | Refreshes the helpers and records an exact commit or tag |
| `tests/` | GC finalizer and integration tests |

## Work against a checkout

Lay out the repositories side by side:

```text
checkouts/
  lvgl-micropython/
  lvgl-bindings/
  micropython/
```

To build exactly the pinned bindings from a checkout of your own:

```bash
git -C lvgl-bindings checkout "$(cat lvgl-micropython/LVGL_BINDINGS_COMMIT)"
git -C lvgl-bindings submodule update --init lvgl
```

A checkout that differs from the pin is built as it is, with a note. To try a
change to the generator, regenerate in lvgl-bindings:

```bash
cd lvgl-bindings
git submodule update --init lvgl
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./regenerate_all.sh --target micropython
```

## Sync from lvgl-bindings

Sync only from an immutable source: a full 40-character commit or a release
tag. The script records it in `LVGL_BINDINGS_COMMIT`.

```bash
./scripts/sync_from_lvgl_bindings.sh --ref <40-character-commit-sha>
./scripts/sync_from_lvgl_bindings.sh --ref v9.5.N
```

When a checkout's generated binding, LVGL or `lv_conf.h` differ from the pin,
the build prints a note naming the commit it is building. Only the copy the
build fetches for itself has to match the pin. Don't hand-edit the generated
binding inputs or the synced `fs_driver.py`.

## Test

The smoke suite belongs to the pinned lvgl-bindings source. This repository
doesn't forward or duplicate it. Run it with the interpreter you built:

```bash
./micropython/ports/unix/build-standard/micropython ./lvgl-bindings/tools/test_lvgl_smoke.py
```

The tests in `tests/` check the GC finalizer flag and the integration wiring.

## Releases

lvgl-micropython has no versions of its own. A firmware build takes it from a
commit, and the binding it builds comes from the pinned lvgl-bindings commit.
