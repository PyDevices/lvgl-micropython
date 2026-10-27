![A blue button reading Hello from LVGL on a light gray background](docs/images/hello.png)

# lvgl-micropython

lvgl-micropython is the part of OmniPython that builds LVGL into MicroPython-compatible firmware as a user C module, so `import lvgl as lv` works on any MicroPython port.

Add the module to the manifest your build already uses (MicroPython 1.29 or later), then build as usual. For the unix port, that manifest is `ports/unix/variants/standard/manifest.py`:

```python
include("/path/to/lvgl-micropython/manifest.py")
```

```bash
git clone https://github.com/PyDevices/lvgl-micropython
cd micropython/ports/unix
make
```

The build fetches the matching LVGL bindings itself; you need only `git`.

```python
import lvgl as lv

lv.init()
disp = lv.display_create(240, 120)
disp.set_color_format(lv.COLOR_FORMAT.RGB565)
buf = bytearray(240 * 120 * 2)
disp.set_buffers(buf, None, len(buf), lv.DISPLAY_RENDER_MODE.FULL)
flushed = []
disp.set_flush_cb(lambda d, area, px: (flushed.append(area.get_width()), d.flush_ready()))

button = lv.button(lv.screen_active())
button.center()
label = lv.label(button)
label.set_text("Hello from LVGL")
button.add_event_cb(lambda e: print("clicked"), lv.EVENT.CLICKED, None)
button.send_event(lv.EVENT.CLICKED, None)

lv.tick_inc(50)
lv.refr_now(disp)
print(label.get_text(), "- drew", flushed[-1], "px wide")
```

```text
clicked
Hello from LVGL - drew 240 px wide
```

The picture at the top is the frame that program drew.

[Docs](https://github.com/PyDevices/lvgl-bindings/blob/main/docs/get-started/install.md#micropython-compatible-firmware-with-lvgl-micropython) · [Examples](https://pydevices.github.io/pydevices-examples/pyscript/) · [Roadmap](ROADMAP.md)

OmniPython is made by [PyDevices](https://pydevices.com).
