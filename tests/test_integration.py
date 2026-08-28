from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bindings_pin_is_an_exact_commit():
    pin = (ROOT / "LVGL_BINDINGS_COMMIT").read_text().strip()
    assert len(pin) == 40
    assert all(character in "0123456789abcdef" for character in pin)


def test_make_and_cmake_builds_enforce_the_pin():
    make = (ROOT / "micropython.mk").read_text()
    cmake = (ROOT / "micropython.cmake").read_text()
    for text in (make, cmake):
        assert "LVGL_BINDINGS_COMMIT" in text
        assert "generated/lvgl_micropython.c" in text
        assert "regenerate_lvmp.sh" not in text


def test_no_consumer_smoke_wrapper_remains():
    assert not (ROOT / "tools" / "test_lvgl_unix.py").exists()
