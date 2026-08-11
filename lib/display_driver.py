# SPDX-FileCopyrightText: 2024 Brad Barnett
# SPDX-FileCopyrightText: 2021 Amir Gonnen (event_loop; MIT)
#
# SPDX-License-Identifier: MIT

"""
display_driver.py - LVGL display/input wiring and event loop for pydisplay.

Canonical copy lives in PyDevices/lv_bindings (``python/display_driver.py``).
Consumer repos (lv_micropython_cmod, lv_circuitpython_mod, lv_cpython_mod)
vendor a synced copy; do not edit those copies directly.

Requires a valid board_config.py on the path (pydisplay). Importing this module
initializes LVGL, starts the shared ``event_loop`` (tick via ``runtime.on_tick``),
and registers display flush + input devices.

``event_loop`` was adapted from upstream lv_utils (Amir Gonnen). Integration
changes kept intentionally small:

* Periodic tick from ``eventsys.Runtime.on_tick`` instead of ``machine.Timer``.
* ``asyncio`` from ``multimer``.
* Sync path runs ``lv.task_handler()`` from the tick callback (re-entrancy
  guarded); the runtime timer already delivers on the main thread.
* Async mode arms the refresh task lazily on the first timer tick so module-top
  ``import display_driver`` is safe before any event loop exists.
* No app-loop helper — LVGL apps call ``runtime.run_forever()``.

Interactive desktop (librt + REPL): ``task_handler`` / indev reads are paced at
``LVGL_PERIOD_MS`` (10 ms) with a wall-clock gate. Display refresh stays at
LVGL's ``LV_DEF_REFR_PERIOD`` (~33 ms). PARTIAL ``show()`` is gated to that
refresh cadence so presents do not track the faster task loop. The Runtime
timer stays at 10 ms; a host-pump subscription drains SDL/keys every tick so
the window cannot stall while LVGL is paused or slow.
"""

import gc
import sys

from board_config import display_drv, runtime

# board_config.Runtime arms machine.Timer immediately. Halt it before any
# LVGL import/init: a soft-timer callback during lv_init / module load has
# corrupted draw_buf handlers on ESP32-P4 (Illegal instruction in
# width_to_stride). main() re-arms after DisplayDriver exists.
if runtime is not None:
    runtime.stop_timer()

import lvgl as lv

import eventsys
import events
import keys

try:
    from multimer import asyncio, loop_running, ticks_add, ticks_diff, ticks_ms
except ImportError:
    asyncio = None
    loop_running = None
    ticks_add = None
    ticks_diff = None
    ticks_ms = None

asyncio_available = asyncio is not None

LVGL_PERIOD_MS = 10
# Match LV_DEF_REFR_PERIOD in lv_conf.h — PARTIAL present cadence / display refresh.
LVGL_REFR_PERIOD_MS = 33
_driver_ref = None  # primary DisplayDriver (compat)
_drivers = []  # all DisplayDriver instances
_host_pump_sub = None
_present_next_ok_ms = None


def _asyncio_loop_running():
    """True when an asyncio loop is already running (host loop or inside a task)."""
    if loop_running is None:
        return False
    return loop_running()


class event_loop:
    """LVGL task loop driven by ``eventsys.Runtime.on_tick``.

    One instance may be active at a time. Sync mode runs ``lv.task_handler``
    from the shared timer; async mode signals an asyncio refresh task.
    Prefer ``import display_driver`` (module ``main()``) over constructing this
    by hand unless you need custom ``freq`` / ``asynchronous`` settings.
    """

    _current_instance = None

    def __init__(
        self,
        freq=None,
        max_scheduled=2,
        refresh_cb=None,
        asynchronous=False,
        exception_sink=None,
        period_ms=None,
    ):
        """Create and register the LVGL event loop.

        Args:
            freq: Desired Hz when ``period_ms`` is omitted (period = ``1000 // freq``).
            max_scheduled: Kept for lv_utils API parity (unused).
            refresh_cb: Optional zero-arg callable after each successful
                ``lv.task_handler()``.
            asynchronous: When True, drive LVGL via an asyncio refresh task.
            exception_sink: Callable receiving exceptions from task handling;
                defaults to :meth:`default_exception_sink`.
            period_ms: Explicit tick period in milliseconds (overrides ``freq``).

        Raises:
            RuntimeError: Another loop is already running, ``runtime`` is
                missing, or async mode is requested without asyncio.
        """
        if self.is_running():
            raise RuntimeError("Event loop is already running!")

        if not lv.is_initialized():
            lv.init()

        event_loop._current_instance = self

        if period_ms is not None:
            self.delay = int(period_ms)
        elif freq is not None:
            self.delay = max(1, 1000 // int(freq))
        else:
            self.delay = LVGL_PERIOD_MS

        self.refresh_cb = refresh_cb
        self.exception_sink = exception_sink if exception_sink else self.default_exception_sink
        # Start paused and do not arm machine.Timer until ``enable()``. On
        # ESP32-P4, even a no-op timer callback interrupting SPIRAM
        # ``draw_buf_create`` corrupts LVGL handlers (Illegal instruction,
        # MTVAL often an ASCII fragment like ``star``).
        self._pause = 1
        self._in_task = False
        self._next_ok_ms = None
        self._last_tick_ms = None

        self.asynchronous = asynchronous
        self.refresh_task = None
        self._timer_sub = None
        self._async_armed = False

        if runtime is None:
            raise RuntimeError("LVGL requires board_config.runtime")

        if self.asynchronous:
            if not asyncio_available:
                raise RuntimeError("Cannot run asynchronous event loop. asyncio is not available!")
            self.refresh_event = asyncio.Event()
            if _asyncio_loop_running():
                self.arm()
        # Sync: defer ``on_tick`` until first ``enable()`` (see ``_arm_sync_timer``).

    def _arm_sync_timer(self):
        """Subscribe the sync tick once; safe to call repeatedly."""
        if self.asynchronous:
            return
        # runtime.stop_timer() deinits the HW timer and clears callbacks but
        # does not notify us — drop a stale handle so we can re-subscribe.
        if self._timer_sub is not None:
            if runtime is not None and runtime._timer is not None:
                return
            self._timer_sub = None
        self._timer_sub = runtime.on_tick(self.timer_cb, period=self.delay, async_=False)

    def arm(self):
        """Create the async refresh task + shared timer once a loop is running.

        No-op in sync mode or when already armed. Safe to call repeatedly.
        """
        if not self.asynchronous or self._async_armed:
            return
        self._async_armed = True
        self.refresh_task = asyncio.create_task(self.async_refresh())
        self._timer_sub = runtime.on_tick(self.timer_cb, period=self.delay, async_=True)

    def deinit(self):
        """Stop the tick subscription / async task and clear the singleton."""
        if getattr(self, "_timer_sub", None) is not None:
            self._timer_sub.deinit()
            self._timer_sub = None
        if self.asynchronous and self.refresh_task is not None:
            self.refresh_task.cancel()
            self.refresh_task = None
        self._async_armed = False
        event_loop._current_instance = None

    def disable(self):
        """Pause LVGL task handling (re-entrant; pair with :meth:`enable`)."""
        # Pause LVGL task handling (e.g. while building the UI). Re-entrant.
        self._pause += 1

    def enable(self):
        """Resume LVGL task handling after :meth:`disable`; arms the sync timer."""
        if self._pause > 0:
            self._pause -= 1
        if self._pause == 0:
            self._arm_sync_timer()
            # Async path: arm refresh task + timer_cb if import-time construction
            # could not (MicroPython lacks get_running_loop; UI builders that
            # disable()/enable() around layout also land here).
            if self.asynchronous and not self._async_armed and _asyncio_loop_running():
                self.arm()

    @staticmethod
    def is_running():
        """True when an :class:`event_loop` instance is currently registered."""
        return event_loop._current_instance is not None

    @staticmethod
    def current_instance():
        """Return the active :class:`event_loop`, or ``None``."""
        return event_loop._current_instance

    def task_handler(self, _=None):
        """Run ``lv.task_handler()`` once when not paused and not nested."""
        if self._in_task or self._pause > 0:
            return
        self._in_task = True
        try:
            if lv._nesting.value == 0:
                lv.task_handler()
                if self.refresh_cb:
                    self.refresh_cb()
        except Exception as e:
            if self.exception_sink:
                self.exception_sink(e)
        finally:
            self._in_task = False

    def tick(self):
        """Manually invoke the timer callback once (same path as the shared timer)."""
        self.timer_cb(None)

    def run(self):
        """Blocking forever-tick loop (macOS only; prefer ``runtime.run_forever()``)."""
        if sys.platform == "darwin":
            while True:
                self.tick()

    def _gate_allows(self):
        if ticks_ms is None or self._next_ok_ms is None:
            return True
        # Positive diff means _next_ok_ms is still in the future.
        return ticks_diff(self._next_ok_ms, ticks_ms()) <= 0

    def _arm_gate(self):
        if ticks_ms is None or ticks_add is None:
            return
        # Pace from completion so a slow flush cannot be immediately followed
        # by another (RT-signal backlog under micropython -i).
        self._next_ok_ms = ticks_add(ticks_ms(), self.delay)

    def timer_cb(self, t):
        """Shared-timer callback: advance LVGL time and run/signal task handling.

        Args:
            t: Timer instance (ignored; may be ``None`` from :meth:`tick`).
        """
        # Called from the runtime's shared timer (on the main thread).
        # In async mode the AsyncTimer fires from inside the running asyncio
        # loop, so we can safely arm (create the refresh task) on the first
        # tick -- no need for an external coordinator.
        if self.asynchronous and not self._async_armed:
            self.arm()
        # Advance LVGL time by real elapsed ms. The present-frame gate may
        # skip task_handler when show()/flush is slow (mipidsi ~30ms); if we
        # also skipped tick_inc there, timers ran at ~half wall-clock speed.
        if ticks_ms is not None:
            now = ticks_ms()
            if self._last_tick_ms is None:
                self._last_tick_ms = now
            elapsed = ticks_diff(now, self._last_tick_ms)
            if elapsed > 0:
                lv.tick_inc(elapsed)
                self._last_tick_ms = now
        if not self._gate_allows():
            return
        if self._pause > 0:
            self._arm_gate()
            return
        if self.asynchronous:
            self.refresh_event.set()
            self._arm_gate()
        else:
            self.task_handler()
            self._arm_gate()

    async def async_refresh(self):
        """Asyncio task body: wait for refresh signals and run ``lv.task_handler``."""
        while True:
            await self.refresh_event.wait()
            if lv._nesting.value == 0:
                self.refresh_event.clear()
                try:
                    lv.task_handler()
                except Exception as e:
                    if self.exception_sink:
                        self.exception_sink(e)
                if self.refresh_cb:
                    self.refresh_cb()
                self._arm_gate()

    def default_exception_sink(self, e):
        """Print ``e`` with traceback to stderr (default :attr:`exception_sink`)."""
        sys.print_exception(e)


def main():
    """Initialize LVGL, wire :class:`DisplayDriver`, and enable the event loop.

    Called automatically on ``import display_driver`` when ``board_config``
    provides ``display_drv`` / ``runtime``.
    """
    global _driver_ref, _drivers, _host_pump_sub
    gc.collect()
    if not lv.is_initialized():
        lv.init()
    # board_config.Runtime arms machine.Timer immediately. Halt every
    # machine.Timer callback before SPIRAM draw_buf_create; re-arm only after
    # buffers exist.
    if runtime is not None:
        runtime.stop_timer()
    loop_inst = event_loop.current_instance()
    if loop_inst is not None:
        # Already-running loop: pause around driver (re)construction.
        loop_inst.disable()
    try:
        if lv.group_get_default() is None:
            lv.group_create().set_default()

        devs = runtime.devices if runtime is not None else []
        _driver_ref = DisplayDriver(
            display_drv,
            devs,
        )
        _drivers = [_driver_ref]
        # Start event_loop only after draw buffers exist (sync path defers
        # on_tick until enable(); still construct after DisplayDriver so
        # host_pump / service cannot arm the shared timer early).
        if loop_inst is None:
            if runtime is not None:
                runtime.claim_display_refresh()
            # PARTIAL: present after every task_handler (blit already wrote the
            # panel FB). Shared DIRECT: present only from flush_is_last.
            loop_inst = event_loop(
                period_ms=LVGL_PERIOD_MS,
                asynchronous=runtime.timer_async if runtime is not None else False,
                refresh_cb=_present_lvgl_displays,
            )
        _ensure_host_pump()
        # Restore Runtime auto-service (touch / QUIT) cleared by stop_timer().
        if runtime is not None:
            runtime._arm_service()
    finally:
        if loop_inst is not None:
            loop_inst.enable()

    if runtime is not None:

        def _lvgl_shutdown_before_quit():
            # Runs from Runtime._handle_quit (device QUIT or at-exit) before the
            # shared timer stops and the display is released. Tear LVGL down in
            # order: stop the event loop, then lv.deinit() to release LVGL's C
            # state so nothing dereferences it during interpreter finalization.
            global _host_pump_sub
            if _host_pump_sub is not None:
                try:
                    _host_pump_sub.deinit()
                except Exception:
                    pass
                _host_pump_sub = None
            inst = event_loop.current_instance()
            if inst is not None:
                inst.deinit()
            try:
                if lv.is_initialized():
                    lv.deinit()
            except Exception:
                pass

        runtime.before_quit = _lvgl_shutdown_before_quit


def _ensure_host_pump():
    """Keep HOST/SDL draining on the 10 ms Runtime tick for all drivers."""
    global _host_pump_sub
    if runtime is None:
        return
    if _host_pump_sub is not None and runtime._timer is not None:
        return
    if _host_pump_sub is not None:
        # Either stop_timer() dropped every subscription, or the timer is an
        # AsyncTimer still waiting for its loop. Drop our callback in the second
        # case so re-subscribing cannot pump the host twice per tick.
        try:
            _host_pump_sub.deinit()
        except Exception:
            pass
        _host_pump_sub = None

    def _host_pump(_t):
        for drv in _drivers:
            for vd in getattr(drv, "virtual_devices", ()):
                vd.poll_host_device()

    # Follow the runtime's timer mode. Forcing async_=False would create the
    # shared *sync* timer whenever the pump subscribes first — which is what a
    # module-scope ``import display_driver`` does under timer_async, locking the
    # app out of AsyncTimer for the rest of the run.
    _host_pump_sub = runtime.on_tick(
        _host_pump, period=10, async_=runtime.timer_async
    )


def _present_lvgl_displays():
    """Present PARTIAL panels after ``lv.task_handler`` (DIRECT shows in flush).

    Gated to :data:`LVGL_REFR_PERIOD_MS` so a faster ``task_handler`` loop does
    not present every tick. DIRECT / shared-FB paths present from flush instead.
    """
    global _present_next_ok_ms
    if ticks_ms is not None and ticks_diff is not None and ticks_add is not None:
        now = ticks_ms()
        if _present_next_ok_ms is not None and ticks_diff(_present_next_ok_ms, now) > 0:
            return
        _present_next_ok_ms = ticks_add(now, LVGL_REFR_PERIOD_MS)
    for drv in _drivers:
        if getattr(drv, "_share_fb", False):
            continue
        panel = getattr(drv, "display_drv", None)
        if panel is None or not callable(getattr(panel, "show", None)):
            continue
        try:
            panel.show()
        except Exception:
            pass


def attach(display, devices=None, *, color_format=None, blocking=True):
    """Attach an additional displaydev panel as an LVGL display.

    Call after ``import display_driver`` (primary already wired) and after
    ``runtime.add_display(display)``.

    Args:
        display: Secondary displaydev driver.
        devices: Optional eventsys devices to bind as indevs on this display.
            When omitted and ``runtime.host_dev`` exists, that host device is
            reused (window-filtered) so the secondary panel receives pointer
            input.
        color_format: LVGL color format; default RGB565.
        blocking: Passed to :class:`DisplayDriver`.

    Returns:
        DisplayDriver: The new bridge instance.
    """
    global _drivers
    if not lv.is_initialized():
        raise RuntimeError("import display_driver before attach()")
    if devices is None:
        devices = []
        if runtime is not None and getattr(runtime, "host_dev", None) is not None:
            devices = [runtime.host_dev]
    kwargs = {"devs": devices, "blocking": blocking}
    if color_format is not None:
        kwargs["color_format"] = color_format
    drv = DisplayDriver(display, **kwargs)
    _drivers.append(drv)
    loop_inst = event_loop.current_instance()
    if loop_inst is not None:
        loop_inst.refresh_cb = _present_lvgl_displays
    _ensure_host_pump()
    return drv


def attach_devices(devs, lv_display=None):
    """Register eventsys devices as LVGL indevs without creating a display.

    Args:
        devs: Iterable of eventsys devices (encoder, keypad, pointer, …).
        lv_display: Target ``lv.display``; default is the primary LVGL display.

    Returns:
        list: Virtual devices accumulated by :func:`create_devices`.
    """
    if lv_display is None:
        if not _drivers:
            raise RuntimeError("no LVGL display; import display_driver first")
        lv_display = _drivers[0].lv_display
    return create_devices(devs, lv_display)


def _touch_state_for(device):
    """Per-pointer touch state (must not be module-global — multi-display)."""
    st = getattr(device, "_lv_touch", None)
    if st is None:
        st = {"x": 0, "y": 0, "pressed": False}
        device._lv_touch = st
    return st


def _make_touch_cb(device):
    """Build a pointer event_cb that updates only ``device``'s touch state."""

    def _touch_cb(event, indev, data):
        st = _touch_state_for(device)
        if event is not None:
            if event.type == events.MOUSEBUTTONDOWN and event.button == 1:
                st["x"], st["y"] = event.pos
                st["pressed"] = True
            elif event.type == events.MOUSEMOTION and event.buttons[0]:
                st["x"], st["y"] = event.pos
            elif event.type == events.MOUSEBUTTONUP and event.button == 1:
                st["x"], st["y"] = event.pos
                st["pressed"] = False
        data.point = lv.point_t({"x": st["x"], "y": st["y"]})
        data.state = lv.INDEV_STATE.PRESSED if st["pressed"] else lv.INDEV_STATE.RELEASED

    return _touch_cb


# CPython: module-level lv.indev_gesture_recognizers_*; MP/CP: indev methods.
_GESTURE_UPDATE = hasattr(lv, "indev_touch_data_t")
# LVGL ``LV_GESTURE_MAX_POINTS`` is 2; finger id is stored as int8_t (-1 = free).
_MAX_GESTURE_TOUCHES = 2
# Windows/pygame often flickers or renumbers finger_id mid-pinch. Track by
# position → stable LVGL slots 0/1, and hold a slot briefly after the OS drops it
# so LVGL does not cancel ONGOING pinch (requires finger_cnt == 2).
_GESTURE_STICKY_MS = 250
_gesture_touches = None
# id(device) -> {slot: (x, y, last_ms)}
_gesture_slots = {}


def _gesture_tick_ms():
    try:
        return int(lv.tick_get())
    except Exception:
        return 0


def _gesture_dist2(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def _gesture_track_slots(dev_key, points, now):
    """Map live contacts to stable slots 0..1 by nearest prior position.

    Returns (pressed dict slot→(x,y), released slot list).
    """
    live = [(int(pt[0]), int(pt[1])) for pt in points]
    prev = _gesture_slots.get(dev_key) or {}
    new_slots = {}
    assigned_live = set()

    # Match against last-known positions (ignore OS finger_id churn).
    if live and prev:
        slot_ids = list(prev.keys())
        if len(live) == 2 and len(slot_ids) == 2:
            s0, s1 = slot_ids[0], slot_ids[1]
            d_same = _gesture_dist2(live[0], prev[s0][:2]) + _gesture_dist2(live[1], prev[s1][:2])
            d_swap = _gesture_dist2(live[0], prev[s1][:2]) + _gesture_dist2(live[1], prev[s0][:2])
            if d_same <= d_swap:
                new_slots[s0] = (live[0][0], live[0][1], now)
                new_slots[s1] = (live[1][0], live[1][1], now)
            else:
                new_slots[s1] = (live[0][0], live[0][1], now)
                new_slots[s0] = (live[1][0], live[1][1], now)
            assigned_live = {0, 1}
        else:
            pairs = []
            for li, xy in enumerate(live):
                for s, (sx, sy, _) in prev.items():
                    pairs.append((_gesture_dist2(xy, (sx, sy)), li, s))
            pairs.sort()
            used_s = set()
            for _, li, s in pairs:
                if li in assigned_live or s in used_s:
                    continue
                assigned_live.add(li)
                used_s.add(s)
                x, y = live[li]
                new_slots[s] = (x, y, now)

    for li, xy in enumerate(live):
        if li in assigned_live:
            continue
        for s in range(_MAX_GESTURE_TOUCHES):
            if s not in new_slots:
                new_slots[s] = (xy[0], xy[1], now)
                assigned_live.add(li)
                break

    # Hold dropped contacts briefly only while another contact is still live
    # (pinch 2→1 flicker). On a full lift, clear immediately so the pointer
    # RELEASED / SHORT_CLICKED path is not blocked by a sticky PRESSED slot.
    if live:
        for s, (x, y, t) in prev.items():
            if s in new_slots:
                continue
            age = (now - t) & 0xFFFFFFFF
            if age <= _GESTURE_STICKY_MS and len(new_slots) < _MAX_GESTURE_TOUCHES:
                new_slots[s] = (x, y, t)

    released = [s for s in prev if s not in new_slots]
    _gesture_slots[dev_key] = new_slots
    pressed = {s: (xy[0], xy[1]) for s, xy in new_slots.items()}
    return pressed, released


def _gesture_recognizers_update(indev, touches, touch_cnt):
    fn = getattr(lv, "indev_gesture_recognizers_update", None)
    if fn is not None:
        fn(indev, touches, touch_cnt)
    else:
        indev.gesture_recognizers_update(touches, touch_cnt)


def _gesture_recognizers_set_data(indev, data):
    fn = getattr(lv, "indev_gesture_recognizers_set_data", None)
    if fn is not None:
        fn(indev, data)
    else:
        indev.gesture_recognizers_set_data(data)


def _configure_gesture_recognizers(indev):
    """Tune LVGL multitouch recognizers so pinch is not stolen.

    Upstream ``lv_indev_gesture_detect_rotation`` zero-inits its config; with
    ``rotation_angle_rad_threshold == 0``, any tiny twist becomes RECOGNIZED
    and ``recognizers_update`` resets the still-ONGOING pinch. Two-finger
    swipe can steal the same way once the contact center moves
    ``gesture_min_distance`` pixels.
    """
    if not _GESTURE_UPDATE:
        return

    set_rot = getattr(lv, "indev_set_rotation_rad_threshold", None)
    if set_rot is not None:
        set_rot(indev, 3.5)
    elif hasattr(indev, "set_rotation_rad_threshold"):
        indev.set_rotation_rad_threshold(3.5)

    set_md = getattr(lv, "indev_set_gesture_min_distance", None)
    if set_md is not None:
        set_md(indev, 255)
    elif hasattr(indev, "set_gesture_min_distance"):
        indev.set_gesture_min_distance(255)

    # Laptop touchscreens rarely hit the stock 0.75 / 1.5 pinch gates cleanly.
    set_down = getattr(lv, "indev_set_pinch_down_threshold", None)
    set_up = getattr(lv, "indev_set_pinch_up_threshold", None)
    if set_down is not None:
        set_down(indev, 0.92)
    elif hasattr(indev, "set_pinch_down_threshold"):
        indev.set_pinch_down_threshold(0.92)
    if set_up is not None:
        set_up(indev, 1.12)
    elif hasattr(indev, "set_pinch_up_threshold"):
        indev.set_pinch_up_threshold(1.12)


def _gesture_feed(indev, data, device):
    """Feed multipoint contacts into LVGL gesture recognizers when available."""
    global _gesture_touches
    if not _GESTURE_UPDATE:
        return

    points = getattr(device, "points", None)
    if not points:
        st = _touch_state_for(device)
        points = ((st["x"], st["y"]),) if st["pressed"] else ()

    dev_key = id(device)
    now = _gesture_tick_ms()
    pressed, released = _gesture_track_slots(dev_key, points or (), now)

    count = len(pressed) + len(released)
    if _gesture_touches is None:
        _gesture_touches = lv.indev_touch_data_t(_MAX_GESTURE_TOUCHES)

    if count == 0:
        _gesture_slots[dev_key] = {}
        _gesture_recognizers_update(indev, _gesture_touches, 0)
        _gesture_recognizers_set_data(indev, data)
        return

    n = count if count <= _MAX_GESTURE_TOUCHES else _MAX_GESTURE_TOUCHES
    ts = now
    idx = 0
    for contact_id, (x, y) in pressed.items():
        if idx >= n:
            break
        t = _gesture_touches[idx]
        t.point = lv.point_t({"x": x, "y": y})
        t.state = lv.INDEV_STATE.PRESSED
        t.id = contact_id
        t.timestamp = ts
        idx += 1
    for contact_id in released:
        if idx >= n:
            break
        t = _gesture_touches[idx]
        t.point = lv.point_t({"x": 0, "y": 0})
        t.state = lv.INDEV_STATE.RELEASED
        t.id = contact_id
        t.timestamp = ts
        idx += 1

    _gesture_recognizers_update(indev, _gesture_touches, idx)
    _gesture_recognizers_set_data(indev, data)
    st = _touch_state_for(device)
    data.point = lv.point_t({"x": st["x"], "y": st["y"]})


def _encoder_cb(event, indev, data):
    if event is None:
        return
    if event.type == events.MOUSEWHEEL:
        data.enc_diff = event.x if event.flipped is False else -event.x
    elif event.type == events.MOUSEBUTTONDOWN and event.button == 3:
        data.state = lv.INDEV_STATE.PRESSED
    elif event.type == events.MOUSEBUTTONUP and event.button == 3:
        data.state = lv.INDEV_STATE.RELEASED


# US QWERTY unshifted → shifted printable (SDL often reports base key + KMOD_SHIFT).
_SHIFT_MAP = {
    ord("`"): ord("~"),
    ord("1"): ord("!"),
    ord("2"): ord("@"),
    ord("3"): ord("#"),
    ord("4"): ord("$"),
    ord("5"): ord("%"),
    ord("6"): ord("^"),
    ord("7"): ord("&"),
    ord("8"): ord("*"),
    ord("9"): ord("("),
    ord("0"): ord(")"),
    ord("-"): ord("_"),
    ord("="): ord("+"),
    ord("["): ord("{"),
    ord("]"): ord("}"),
    ord("\\"): ord("|"),
    ord(";"): ord(":"),
    ord("'"): ord('"'),
    ord(","): ord("<"),
    ord("."): ord(">"),
    ord("/"): ord("?"),
}


def _modifier_bit(event):
    """Return ``KMOD_*`` bit for a modifier key event, or 0."""
    k = event.key
    name = getattr(event, "name", None) or ""
    by_key = {
        keys.K_LSHIFT: keys.KMOD_LSHIFT,
        keys.K_RSHIFT: keys.KMOD_RSHIFT,
        keys.K_LCTRL: keys.KMOD_LCTRL,
        keys.K_RCTRL: keys.KMOD_RCTRL,
        keys.K_LALT: keys.KMOD_LALT,
        keys.K_RALT: keys.KMOD_RALT,
        keys.K_LGUI: keys.KMOD_LGUI,
        keys.K_RGUI: keys.KMOD_RGUI,
    }
    bit = by_key.get(k)
    if bit:
        return bit
    by_name = {
        "Left Shift": keys.KMOD_LSHIFT,
        "Right Shift": keys.KMOD_RSHIFT,
        "Left Ctrl": keys.KMOD_LCTRL,
        "Right Ctrl": keys.KMOD_RCTRL,
        "Left Alt": keys.KMOD_LALT,
        "Right Alt": keys.KMOD_RALT,
        "Left GUI": keys.KMOD_LGUI,
        "Right GUI": keys.KMOD_RGUI,
    }
    return by_name.get(name, 0)


def _apply_mods(k, mod):
    """Apply Shift/Caps to a printable ASCII codepoint."""
    shift = bool(mod & keys.KMOD_SHIFT)
    caps = bool(mod & keys.KMOD_CAPS)
    if 97 <= k <= 122:  # a-z
        if shift ^ caps:
            return k - 32
        return k
    if 65 <= k <= 90:  # A-Z
        if shift ^ caps:
            return k
        return k + 32
    if shift and k in _SHIFT_MAP:
        return _SHIFT_MAP[k]
    return k


def _lv_key_from_event(event, tracked_mods=0):
    """Map eventsys/SDL key codes to ``lv.KEY_*`` / Unicode for the keypad indev.

    Arrows become caret keys (``lv.KEY.LEFT``/…). Tab still moves group focus
    (``NEXT`` / ``PREV``). Modifier keys are not returned — they corrupt text
    widgets if inserted as huge SDLK values. Printable ASCII gets Shift/Caps
    via ``event.mod`` and optional ``tracked_mods``.

    Returns ``None`` for keys that must not update the LVGL keypad.
    """
    k = event.key
    name = getattr(event, "name", None) or ""
    mod = (getattr(event, "mod", 0) or 0) | (tracked_mods or 0)

    if _modifier_bit(event):
        return None

    # Scancode-derived SDLK → character / control (if a host skipped sdldisplay normalize).
    if isinstance(k, int) and (k & 0x40000000) and name:
        if len(name) == 1:
            k = ord(name.lower())
        elif name == "Space":
            k = 32
        elif name == "Return":
            k = keys.K_RETURN
        elif name == "Backspace":
            k = keys.K_BACKSPACE
        elif name == "Escape":
            k = keys.K_ESCAPE
        elif name == "Tab":
            k = keys.K_TAB
        elif name == "Delete":
            k = keys.K_DELETE

    if k == keys.K_TAB or name == "Tab":
        if mod & keys.KMOD_SHIFT:
            return lv.KEY.PREV
        return lv.KEY.NEXT
    if k == keys.K_RIGHT or name == "Right":
        return lv.KEY.RIGHT
    if k == keys.K_LEFT or name == "Left":
        return lv.KEY.LEFT
    if k == keys.K_DOWN or name == "Down":
        return lv.KEY.DOWN
    if k == keys.K_UP or name == "Up":
        return lv.KEY.UP
    if k in (keys.K_RETURN, keys.K_KP_ENTER) or name == "Return":
        return lv.KEY.ENTER
    if k == keys.K_ESCAPE or name == "Escape":
        return lv.KEY.ESC
    if k == keys.K_BACKSPACE or name == "Backspace":
        return lv.KEY.BACKSPACE
    if k == keys.K_DELETE or name == "Delete":
        return lv.KEY.DEL
    if k == keys.K_HOME or name == "Home":
        return lv.KEY.HOME
    if k == keys.K_END or name == "End":
        return lv.KEY.END
    if not isinstance(k, int) or not (32 <= k <= 126):
        return None
    return _apply_mods(k, mod)


def _make_keypad_cb(device):
    """Build a keypad event_cb that always writes press state (idle-safe)."""
    st = getattr(device, "_lv_key", None)
    if st is None:
        st = {"key": 0, "pressed": False, "mods": 0}
        device._lv_key = st
    else:
        st.setdefault("mods", 0)

    def _keypad_cb(event, indev, data):
        if event is not None:
            bit = _modifier_bit(event)
            if bit:
                if event.type == events.KEYDOWN:
                    st["mods"] |= bit
                elif event.type == events.KEYUP:
                    st["mods"] &= ~bit
            else:
                key = _lv_key_from_event(event, st["mods"])
                if key is not None:
                    if event.type == events.KEYDOWN:
                        st["pressed"] = True
                        st["key"] = key
                    elif event.type == events.KEYUP:
                        st["pressed"] = False
                        st["key"] = key
        data.state = lv.INDEV_STATE.PRESSED if st["pressed"] else lv.INDEV_STATE.RELEASED
        data.key = st["key"]

    return _keypad_cb


def create_devices(devs, lv_display, virtual_devices=None, window_id=None):
    """Register eventsys devices as LVGL indevs (pointer / encoder / keypad).

    Args:
        devs: Iterable of eventsys devices from ``runtime.devices``.
        lv_display: LVGL display object to attach indevs to.
        virtual_devices: Optional list mutated when expanding :class:`HostEventsDevice`
            into virtual pointer/keypad devices.
        window_id: OS window id for host fan-out filtering (multi-display).

    Returns:
        list: Accumulated virtual devices (for host expansion).
    """
    if virtual_devices is None:
        virtual_devices = []
    for device in devs:
        if device.type in (eventsys.POINTER, eventsys.ENCODER, eventsys.KEYPAD):
            indev = lv.indev_create()
            indev.set_display(lv_display)
            device.user_data = indev
            if device.type == eventsys.POINTER:
                event_cb = _make_touch_cb(device)
                device.subscribe(event_cb)
                indev.set_type(lv.INDEV_TYPE.POINTER)
                _configure_gesture_recognizers(indev)
            elif device.type == eventsys.ENCODER:
                event_cb = _encoder_cb
                device.subscribe(event_cb)
                indev.set_type(lv.INDEV_TYPE.ENCODER)
            elif device.type == eventsys.KEYPAD:
                event_cb = _make_keypad_cb(device)
                device.subscribe(event_cb)
                indev.set_type(lv.INDEV_TYPE.KEYPAD)

            # LVGL calls read_cb every period with (indev, data). device.poll
            # only invokes subscribers when there is a new event, so idle
            # reads never wrote data.state/point — taps were invisible.
            def _read_cb(indev_obj, data, _dev=device, _cb=event_cb):
                _dev.poll(indev_obj, data)
                _cb(None, indev_obj, data)
                # Host backends drain native input in batches. Ask LVGL to call
                # us again in this read cycle until the virtual-device FIFO is
                # empty, preserving fast KEYDOWN/KEYUP sequences without adding
                # one LVGL refresh period of latency per transition.
                data.continue_reading = bool(getattr(_dev, "has_pending", False))
                if _dev.type == eventsys.POINTER:
                    _gesture_feed(indev_obj, data, _dev)

            indev.set_group(lv.group_get_default())
            indev.set_read_cb(_read_cb)
            # Default indev timer uses LV_DEF_REFR_PERIOD (~33 ms); match task_handler.
            read_timer = indev.get_read_timer()
            if read_timer is not None:
                read_timer.set_period(LVGL_PERIOD_MS)
        elif device.type == eventsys.HOST:
            wid = window_id
            if wid is None:
                host_disp = getattr(device, "_data", None)
                if host_disp is not None:
                    wid = getattr(host_disp, "_window_id", None)
            vd = eventsys.VirtualDevices(device, window_id=wid)
            virtual_devices.append(vd)
            create_devices(vd.devices, lv_display, virtual_devices, window_id=wid)
    return virtual_devices


class DisplayDriver:
    """Bridge a displaydev driver to an LVGL display + input devices.

    Creates the LVGL display, chooses DIRECT (shared framebuffer) or PARTIAL
    render mode, installs flush callbacks, and wires eventsys devices via
    :func:`create_devices`.
    """

    def __init__(
        self,
        display_drv,
        devs=None,
        color_format=lv.COLOR_FORMAT.RGB565,
        blocking=True,
    ):
        """Create LVGL display buffers and register input devices.

        Args:
            display_drv: displaydev driver (BusDisplay, SDLDisplay, FBDisplay, …).
            devs: Iterable of eventsys devices to register as LVGL indevs.
            color_format: LVGL color format (default RGB565).
            blocking: When False, register a bus flush-ready callback for async blit.
        """
        if devs is None:
            devs = []
        gc.collect()
        self.display_drv = display_drv
        if display_drv.requires_byteswap:
            self._needs_swap = display_drv.disable_auto_byteswap(True)
        else:
            self._needs_swap = False
        self._color_size = lv.color_format_get_size(color_format)
        self._blocking = blocking
        self._share_fb = False
        self._draw_buf1 = None
        self._draw_buf2 = None
        # Keep Python refs alive for set_buffers panel views (GC must not free).
        self._fb_share = None

        self.lv_display = lv.display_create(display_drv.width, display_drv.height)
        self.lv_display.set_color_format(color_format)

        share = bool(getattr(display_drv, "share_framebuffer", False))
        # Byteswap + shared FB not supported yet — keep PARTIAL blit path.
        fbs = None
        if share and not self._needs_swap:
            try:
                fbs = display_drv.framebuffers()
            except Exception:
                fbs = None

        if fbs is not None:
            buf1, buf2, nbytes, stride = fbs
            packed = int(display_drv.width) * self._color_size
            self._fb_share = (buf1, buf2)
            self._share_fb = True
            self.lv_display.set_flush_cb(self._flush_cb_direct)
            if (
                stride
                and int(stride) != packed
                and hasattr(self.lv_display, "set_buffers_with_stride")
            ):
                self.lv_display.set_buffers_with_stride(
                    buf1, buf2, int(nbytes), int(stride), lv.DISPLAY_RENDER_MODE.DIRECT
                )
            else:
                self.lv_display.set_buffers(buf1, buf2, int(nbytes), lv.DISPLAY_RENDER_MODE.DIRECT)
        else:
            self._draw_buf1 = lv.draw_buf_create(
                display_drv.width, display_drv.height // 10, color_format, 0
            )
            self._draw_buf2 = lv.draw_buf_create(
                display_drv.width, display_drv.height // 10, color_format, 0
            )
            self.lv_display.set_flush_cb(self._flush_cb)
            if not self._blocking:
                display_drv.display_bus.register_callback(self.lv_display.flush_ready)
            self.lv_display.set_draw_buffers(self._draw_buf1, self._draw_buf2)
            self.lv_display.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)

        self.virtual_devices = create_devices(
            devs,
            self.lv_display,
            window_id=getattr(display_drv, "_window_id", None),
        )

    def _flush_cb_direct(self, disp_drv, area, color_p):
        """DIRECT: LVGL already painted the panel FB; present on last area."""
        panel = self.display_drv
        if hasattr(panel, "_sdl_active") and not panel._sdl_active():
            self.lv_display.flush_ready()
            return
        try:
            last = self.lv_display.flush_is_last()
        except Exception:
            last = True
        synced = False
        flush_rect = getattr(panel, "flush_rect", None)
        if flush_rect is not None:
            try:
                synced = bool(
                    flush_rect(
                        area.x1,
                        area.y1,
                        area.x2 - area.x1 + 1,
                        area.y2 - area.y1 + 1,
                    )
                )
            except Exception:
                synced = False
        if last and not synced:
            try:
                panel.show()
            except Exception:
                pass
        if self._blocking:
            self.lv_display.flush_ready()

    def _flush_cb(self, disp_drv, area, color_p):
        panel = self.display_drv
        if hasattr(panel, "_sdl_active") and not panel._sdl_active():
            self.lv_display.flush_ready()
            return
        width = area.x2 - area.x1 + 1
        height = area.y2 - area.y1 + 1

        if self._needs_swap:
            lv.draw_sw_rgb565_swap(color_p, width * height)

        data = color_p.__dereference__(width * height * self._color_size)
        panel.blit_rect(data, area.x1, area.y1, width, height)
        if self._blocking:
            self.lv_display.flush_ready()


# Import-time bootstrap (same as before the probe split).
main()

# org-secret smoke check 2026-08-02T11:08Z
