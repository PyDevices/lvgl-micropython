#!/usr/bin/env python3
"""Deprecated — use ../lv_bindings/test_lvgl_smoke.py."""
import runpy
import sys
from pathlib import Path

_SMOKE = Path(__file__).resolve().parents[1] / "lv_bindings" / "test_lvgl_smoke.py"
if not _SMOKE.is_file():
    sys.exit("Missing unified smoke test: {}".format(_SMOKE))
runpy.run_path(str(_SMOKE), run_name="__main__")
