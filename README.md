# lvgl-micropython

MicroPython user C module glue for LVGL: `micropython.mk`, CMake usermod, GC-aware allocator, and smoke tests.

New here? Read the [newcomer's guide](docs/newcomers.md) for the generated-
bindings boundary, runtime entrypoint, and MicroPython integration map.

This repo is a consumer/build repo for the LVGL stack: it consumes generated bindings from lvgl-bindings and rebuilds MicroPython targets, but does not publish its own package. See [lvgl-bindings — The LVGL family](https://github.com/PyDevices/lvgl-bindings#the-lvgl-family) for how the family fits together.

Requires a sibling clone of [lvgl-bindings](https://github.com/PyDevices/lvgl-bindings) whose generated binding inputs match the exact commit recorded in `LVGL_BINDINGS_COMMIT`. The Make and CMake integrations reject a mismatched source, LVGL pin, or configuration.

**Synced from lvgl-bindings:** `lib/display_driver.py` and `lib/fs_driver.py` are synced from [lvgl-bindings](https://github.com/PyDevices/lvgl-bindings) at the commit pinned in `LVGL_BINDINGS_COMMIT`, along with the generated bindings. Do not edit them here — change them in lvgl-bindings and re-sync.

## Documentation

See [docs/](docs/index.md).

This repo is mostly glue: it wires LVGL into MicroPython builds and exposes the interpreter hooks that the firmware needs. In practice, you usually change the build glue or allocator here when the port itself changes, but you do not regenerate the bindings here. If the binding layer changed, update **`lvgl-bindings`** first and then rebuild this module against the new generated file.

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
./regenerate_all.sh --target micropython
```

## Build

You need [lvgl-bindings](https://github.com/PyDevices/lvgl-bindings) beside
this repository, checked out at the commit in
[LVGL_BINDINGS_COMMIT](LVGL_BINDINGS_COMMIT) with its `lvgl` submodule. Its
generated binding is committed, so there is nothing to generate:

```bash
git clone https://github.com/PyDevices/lvgl-micropython
git clone https://github.com/PyDevices/lvgl-bindings
git -C lvgl-bindings checkout "$(cat lvgl-micropython/LVGL_BINDINGS_COMMIT)"
git -C lvgl-bindings submodule update --init lvgl
```

On MicroPython 1.29 or later, add one line to the manifest your build already
uses:

```python
include("/path/to/lvgl-micropython/manifest.py")
```

On unix that manifest is `ports/unix/variants/standard/manifest.py`; on esp32
and rp2 it is usually `ports/<port>/boards/manifest.py`, unless your board
brings its own. Then build as usual. The include brings in the `lvgl` C module
and freezes two helpers, `display_driver` and `fs_driver`. If lvgl-bindings is
not a sibling, pass `BINDINGS_DIR=/path/to/lvgl-bindings` to `make` on a Make
port. The build stops if that checkout does not match the pin. Tested on the
unix port against MicroPython v1.29.0, where `import lvgl` reports 9.5.

If you would rather not edit the MicroPython tree, write a manifest of your own
and pass it as `FROZEN_MANIFEST=`. That replaces the port's default, so include
the default too (`include("$(PORT_DIR)/variants/standard/manifest.py")` on
unix, `include("$(PORT_DIR)/boards/manifest.py")` on esp32) or you lose
`asyncio` and the port's other frozen modules.

**Older than 1.29?** Manifests there have no `c_module()`, so this one will not
load; use `USER_C_MODULES`, and freeze the two helpers from `lib/` yourself if
you want them. On esp32 and rp2 point it at this repository:

```bash
make BOARD=ESP32_GENERIC_S3 USER_C_MODULES=/abs/path/to/lvgl-micropython
```

On Make ports such as unix point it at the directory that *contains* this
repository, which builds every module in that directory:

```bash
cd micropython/ports/unix && make USER_C_MODULES=../../..
```

## JPEG images need displayif

`lv.image` draws PNG and LVGL's own BIN format on any build of this module. It
draws **nothing at all** for a JPEG unless
[displayif](https://github.com/PyDevices/displayif) is in the same firmware.

The decoder moved. `LV_USE_TJPGD` is 0 in the bindings, so LVGL's built-in
JPEG decoder is not compiled in; displayif's `jpegio` registers its own TJpgDec
with LVGL through `lv_image_decoder_create` when the two usermods are built
together. The point was one TJpgDec per firmware instead of two, without
carrying a fork of LVGL — but it means a build of this module alone silently
skips JPEGs at run time rather than failing at build time.

So add displayif when you want JPEG, with a second line in the same manifest:

```python
include("/path/to/lvgl-micropython/manifest.py")
include("/path/to/displayif/manifest.py")
```

(or, before 1.29, `USER_C_MODULES="/abs/path/to/lvgl-micropython;/abs/path/to/displayif"`).

Both build files print a note when they cannot see displayif, so you are told
at build time rather than finding out from a blank image. From the displayif
side, `jpegio.register_lvgl_decoder()` and `jpegio.lvgl_decoders()` exist on
every build and report what happened.

## Build with other user C modules (optional)

To build several user C modules together across ports, name them in one
manifest: this repository's `manifest.py` carries `c_module(".")`, and a
manifest that `include()`s several such files builds them all. The
[micropython-pydevices](https://github.com/PyDevices/micropython-pydevices)
repository keeps ready-made presets (`manifests/lvgl.py` is this module with
displayif) and out-of-tree variants and boards, so with the repositories as
siblings of a MicroPython checkout it is upstream's own make and nothing else:

```bash
cd micropython/ports/unix
make VARIANT_DIR=../../../micropython-pydevices/variants/unix/pydevices \
     FROZEN_MANIFEST=../../../micropython-pydevices/manifests/lvgl.py
```

## App Usage & Timer Model

In MicroPython, `display_driver` uses `machine.Timer` (hardware interrupts):
- **Interactive REPL (`micropython -i` or on-board prompt)**: Simply create widgets and drop out to the prompt. Hardware timer interrupts keep LVGL animations, timers, and touch input running continuously in the background while you inspect variables or test code interactively.
- **Standalone Scripts**: Use `app.run()` if you need an explicit loop for non-interactive desktop scripts.

```python
import display_driver  # noqa: F401 - initializes display, input, and machine.Timer
import lvgl as lv

scr = lv.screen_active()
btn = lv.button(scr)
btn.center()
label = lv.label(btn)
label.set_text("Hello MicroPython LVGL!")

# Dropping out the bottom leaves the UI active in the background!
```

## Smoke test

```bash
./micropython/ports/unix/build-standard/micropython ./lvgl-bindings/tools/test_lvgl_smoke.py
```

The smoke suite belongs to the exact pinned `lvgl-bindings` source; this repo does not forward or duplicate it.

## Files

| Path | Role |
|---|---|
| `micropython.mk` | Make ports (pre-1.29: `USER_C_MODULES` = parent directory) |
| `micropython.cmake` | CMake ports (pre-1.29: `USER_C_MODULES` = this repo) |
| `src/lv_mem_core_micropython.c` | GC-aware LVGL allocator |
| `manifest.py` | Names the C module and freezes `lib/display_driver.py`, `lib/fs_driver.py` (synced from lvgl-bindings) |
| `lib/display_driver.py` | Vendored PyDevices LVGL glue (`import display_driver`) |
| `LVGL_BINDINGS_COMMIT` | Exact generator/artifact source consumed by builds |
| `scripts/sync_from_lvgl_bindings.sh` | Refresh helpers and record an exact commit/tag |

CircuitPython integration lives in [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython).
