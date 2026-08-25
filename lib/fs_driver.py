# SPDX-FileCopyrightText: 2024 Brad Barnett
# SPDX-FileCopyrightText: mhepp (original, from lv_binding_micropython; MIT)
#
# SPDX-License-Identifier: MIT

"""
fs_driver.py - register a Python-backed LVGL filesystem driver.

Canonical copy lives in PyDevices/lvgl-bindings (``python/fs_driver.py``).
Consumer repos (lvgl-micropython, lvgl-circuitpython, lvgl-python)
vendor a synced copy; do not edit those copies directly.

Note that a change here is a release trigger: this path is watched by
``.github/workflows/trigger-lvgl-python-release.yml``, which dispatches
lvgl-python's sync, and that publishes a new version when the sync produces a
diff. Even a comment-only edit ships a release.

Bridges LVGL's ``lv_fs`` API to the host's ``open()``, so LVGL features that
stream from files work against the platform filesystem (MicroPython VFS,
CircuitPython storage, or CPython) without enabling any ``LV_USE_FS_*`` C
driver. The main customers are runtime-loadable binary fonts and images::

    import lvgl as lv
    import fs_driver

    fs_driver.register("S")
    font = lv.binfont_create("S:fonts/montserrat_20.bin")
    label.set_style_text_font(font, 0)

Streaming through this driver keeps only LVGL's parsed structures in the
heap; the source file is read incrementally (never fully buffered), which
matters for large fonts on small boards. ``lv.binfont_create_from_buffer``
remains the no-driver alternative when holding the whole file in RAM is
acceptable.

Adapted from lv_binding_micropython's ``lib/fs_driver.py`` (author mhepp).
Changes for PyDevices: portable across the three generated bindings and a
``register()`` convenience that owns the ``lv.fs_drv_t`` instance.

Portability note: LVGL stores the handle returned by ``open_cb`` as a raw
``void *``. The MicroPython-style runtimes pass a dict through unchanged and
``Blob.__cast__()`` recovers it; the CPython runtime instead returns the
object's address as an int from ``__cast__()``. ``_handles`` keys every open
handle by ``id()`` (== that address on both runtimes) so one lookup works
everywhere — and it doubles as the reference that keeps the handle alive on
CPython, where LVGL's ``void *`` holds no reference.
"""

import struct

import lvgl as lv

_handles = {}


def _handle(fs_file):
    obj = fs_file.__cast__()
    if isinstance(obj, int):  # CPython runtime: raw address
        return _handles[obj]
    return obj  # MicroPython-style runtime: the dict itself


def fs_open_cb(drv, path, mode):
    if mode == lv.FS_MODE.WR:
        p_mode = "wb"
    elif mode == lv.FS_MODE.RD:
        p_mode = "rb"
    elif mode == lv.FS_MODE.WR | lv.FS_MODE.RD:
        p_mode = "rb+"
    else:
        raise RuntimeError(
            "fs_open_cb() - open mode error, %s is invalid mode" % mode
        )

    try:
        f = open(path, p_mode)  # noqa: SIM115 - closed via fs_close_cb
    except OSError as e:
        raise RuntimeError("fs_open_cb(%s) exception: %s" % (path, e))

    handle = {"file": f, "path": path}
    _handles[id(handle)] = handle
    return handle


def fs_close_cb(drv, fs_file):
    handle = _handle(fs_file)
    _handles.pop(id(handle), None)
    try:
        handle["file"].close()
    except OSError as e:
        raise RuntimeError("fs_close_cb(%s) exception: %s" % (handle["path"], e))
    return lv.FS_RES.OK


def fs_read_cb(drv, fs_file, buf, btr, br):
    handle = _handle(fs_file)
    try:
        data = handle["file"].read(btr)
        buf.__dereference__(btr)[0 : len(data)] = data
        br.__dereference__(4)[0:4] = struct.pack("<L", len(data))
    except OSError as e:
        raise RuntimeError("fs_read_cb(%s) exception: %s" % (handle["path"], e))
    return lv.FS_RES.OK


def fs_seek_cb(drv, fs_file, pos, whence):
    handle = _handle(fs_file)
    try:
        handle["file"].seek(pos, whence)
    except OSError as e:
        raise RuntimeError("fs_seek_cb(%s) exception: %s" % (handle["path"], e))
    return lv.FS_RES.OK


def fs_tell_cb(drv, fs_file, pos):
    handle = _handle(fs_file)
    try:
        tpos = handle["file"].tell()
        pos.__dereference__(4)[0:4] = struct.pack("<L", tpos)
    except OSError as e:
        raise RuntimeError("fs_tell_cb(%s) exception: %s" % (handle["path"], e))
    return lv.FS_RES.OK


def fs_write_cb(drv, fs_file, buf, btw, bw):
    handle = _handle(fs_file)
    try:
        wr = handle["file"].write(buf.__dereference__(btw)[0:btw])
        bw.__dereference__(4)[0:4] = struct.pack("<L", wr)
    except OSError as e:
        raise RuntimeError("fs_write_cb(%s) exception: %s" % (handle["path"], e))
    return lv.FS_RES.OK


def fs_register(fs_drv, letter, cache_size=500):
    """Wire the callbacks into a caller-owned ``lv.fs_drv_t`` and register it.

    Upstream-compatible entry point (same signature as
    lv_binding_micropython). ``letter`` is the drive prefix used in LVGL
    paths (``"S"`` registers ``S:...``).
    """
    fs_drv.init()
    fs_drv.letter = ord(letter)
    fs_drv.open_cb = fs_open_cb
    fs_drv.read_cb = fs_read_cb
    fs_drv.write_cb = fs_write_cb
    fs_drv.seek_cb = fs_seek_cb
    fs_drv.tell_cb = fs_tell_cb
    fs_drv.close_cb = fs_close_cb

    if cache_size >= 0:
        fs_drv.cache_size = cache_size

    fs_drv.register()
    return fs_drv


# The lv.fs_drv_t must outlive the registration; keep them at module scope,
# one per drive letter.
_registered = {}


def register(letter="S", cache_size=500):
    """Register drive ``letter`` backed by the platform filesystem.

    Idempotent per letter: repeat calls return the existing driver. Paths
    after the colon are passed to ``open()`` verbatim, so ``S:fonts/x.bin``
    opens ``fonts/x.bin`` relative to the current directory and
    ``S:/sd/fonts/x.bin`` opens an absolute path.
    """
    if letter not in _registered:
        _registered[letter] = fs_register(lv.fs_drv_t(), letter, cache_size)
    return _registered[letter]
