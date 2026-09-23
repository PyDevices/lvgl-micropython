# Newcomer's guide to lvgl-micropython

`lvgl-micropython` is the MicroPython build glue for PyDevices' LVGL stack. It
combines the generated LVGL binding tree with MicroPython user-module build
files, a GC-aware allocator, and the Python display helpers used by an
application.

It does not publish a standalone package and it does not generate bindings. It
consumes an exact sibling checkout of
[lvgl-bindings](https://github.com/PyDevices/lvgl-bindings), recorded in
`LVGL_BINDINGS_COMMIT`.

## Start by using the firmware entrypoint

On firmware built with this module, an application starts with the synced
display helper:

```python
import display_driver
import lvgl as lv

screen = lv.screen_active()
button = lv.button(screen)
button.center()
label = lv.label(button)
label.set_text("Hello MicroPython LVGL!")
```

`display_driver` wires the display, input, and timer integration. It needs
pydevices' `appdev`, `events`, and `keys` on the device, plus a `board_config`
unless your code has already created an `appdev.App`. At an interactive
MicroPython prompt, hardware timer callbacks keep LVGL active after the script
reaches the prompt.

## The mental model

```text
lvgl-bindings generator and pinned generated artifacts
                         |
                         v
lvgl-micropython build glue + GC-aware allocator
                         |
                         v
MicroPython firmware module: import lvgl
                         |
                         v
synced display_driver helper -> display/input/timers
```

The Make and CMake integrations reject a mismatched binding source, LVGL pin, or
generated configuration. Update `lvgl-bindings` first, then re-sync here; do not
hand-edit the generated binding inputs or the synced
`display_driver.py`/`fs_driver.py` copies.

## Repository map

| Path | Purpose |
|---|---|
| `micropython.mk` | Make-port user-module entrypoint. |
| `micropython.cmake` | CMake-port user-module entrypoint. |
| `src/lv_mem_core_micropython.c` | GC-aware LVGL allocator. |
| `src/lvgl_micropython_build.c` | `lvgl_micropython.__revision__` build stamp. |
| `lib/display_driver.py` | Synced display, input, and timer helper. |
| `lib/fs_driver.py` | Synced LVGL filesystem helper. |
| `LVGL_BINDINGS_COMMIT` | Exact generated-binding source commit. |
| `scripts/sync_from_lvgl_bindings.sh` | Refresh synced helpers and recorded source. |
| `tests/` | GC finalizer and integration tests. |

## Build boundaries

For Make ports, `USER_C_MODULES` points at the workspace parent that contains
this and other Make user-module repositories. For CMake ports, it points at this
repository or its `micropython.cmake`. The root README contains supported
commands for both shapes and shows how to combine modules.

JPEG is the important optional boundary: LVGL can always display PNG and its BIN
format, but JPEG needs [displayif](https://github.com/PyDevices/displayif) in
the same firmware. displayif's `jpegio` registers the decoder when it sees this
user module; a build without it can otherwise skip JPEGs at runtime.

The `micropython-pydevices` `lvgl.py` manifest is the maintained
multi-repository preset for LVGL plus displayif.

## Contributor boundary

This repository is glue. Change binding generation and synced helper sources in
`lvgl-bindings`, then regenerate and synchronize. Change this repository only
for MicroPython build integration, allocator behavior, or interpreter lifecycle
needs.

A safe first contribution is a focused integration or finalizer test, a
build-documentation correction, or a change backed by the pinned binding smoke
suite. Run the smoke test from the exact pinned lvgl-bindings checkout rather
than duplicating generated-binding coverage here.
