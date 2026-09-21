"""LVGL's allocations must not be flagged as having MicroPython finalisers.

``gc_alloc()``'s second argument is ``alloc_flags``, and 1 is
``GC_ALLOC_FLAG_HAS_FINALISER``. ``lv_malloc_core()`` passed ``true`` there, so
every LVGL struct went on the heap flagged as an object with a ``__del__``.
``gc_sweep_run_finalisers()`` then read each one's first word as an
``mp_obj_base_t`` type pointer -- which worked by luck until an
``lv.deinit()``/``lv.init()`` cycle put a different first word in a block that
had been freed and reused, and ``gc.collect()`` died with SIGBUS
(PyDevices/lvgl-micropython#10).

A build is the real proof and this is a source check, but the flag is one
character and worth pinning: nothing in the bindings ever wanted it (the
generated module defines no ``__del__`` at all).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "lv_mem_core_micropython.c"


def _call_args(function):
    """The gc_* call inside the named lv_*_core function.

    Comments are stripped first: the explanation above the call names
    ``gc_alloc()`` with empty parentheses, and matching that instead of the
    real call is how the first draft of this test passed on broken source.
    """
    text = SOURCE.read_text()
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", " ", text)
    body = text.split("void * %s(" % function, 1)[1].split("\n}", 1)[0]
    match = re.search(r"gc_(?:alloc|realloc)\(([^)]+)\)", body)
    assert match, "no gc_ call found in %s" % function
    return [argument.strip() for argument in match.group(1).split(",")]


def test_lv_malloc_core_does_not_set_the_finaliser_flag():
    args = _call_args("lv_malloc_core")
    assert args[-1] == "0", (
        "lv_malloc_core passes %r as gc_alloc's alloc_flags; anything with bit 0 "
        "set is GC_ALLOC_FLAG_HAS_FINALISER and makes the sweep dereference an "
        "LVGL struct as an mp_obj_base_t" % args[-1]
    )


def test_lv_realloc_core_still_allows_moving():
    # gc_realloc's third argument is allow_move, not a flag word -- true is right.
    args = _call_args("lv_realloc_core")
    assert args[-1] == "true", (
        "lv_realloc_core should let the GC move the block; got %r" % args[-1]
    )
