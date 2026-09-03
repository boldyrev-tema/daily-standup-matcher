"""Menu-bar (macOS status bar) icon that shows/hides a frameless pywebview
window, replacing Dock-based minimize now that the app is hidden from the
Dock (see hide_from_dock()). Shared by all three run_*.py front-ends
(Полоса/Второй экран/Колонка) — same idea, different single-letter label.

Everything here runs on the MAIN thread, called from __main__ before
webview.start(). An earlier version ran pystray's Icon.run() in a background
thread (a pattern seen working in a pywebview GitHub issue thread) — that
crashed hard on this machine: pystray's macOS backend calls its own
NSApplication.run() inside Icon.run(), which collides with pywebview's own
NSApplication.run() on the main thread (confirmed via a real crash report:
EXC_BREAKPOINT/SIGTRAP inside -[NSApplication run] on the pystray thread).
pystray's own run_detached() is the documented fix for embedding into
another library's already-running loop — no thread of ours needed at all;
the loop that ends up servicing the status item's clicks is whichever
NSApplication.run() runs afterward, i.e. pywebview's, entered via
webview.start(). Its default `setup` callback also touches AppKit
(`visible = True`) from ANOTHER background thread it starts internally, so
that default is suppressed here too — visibility is set directly, still on
the main thread.
"""
import threading

import pystray
from PIL import Image, ImageDraw, ImageFont

try:
    import AppKit
    from PyObjCTools import AppHelper

    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False


def defer(delay: float, fn) -> None:
    """Schedule fn to run after `delay` seconds, on the Cocoa main thread —
    NOT on a plain Python timer thread. Every close_window() in this
    project defers window.destroy()/tray_icon.stop() by a short delay so
    the JS-bridge call's own response goes out on a still-live run loop
    first (py-spy-confirmed deadlock otherwise, 2 сен: window.destroy()
    ending the run loop before its own JS response was delivered). The
    delay was originally a threading.Timer — but that fires its callback on
    a THIRD thread (neither main nor the JS-bridge thread), and
    window.destroy() is itself an AppKit call, which AppKit only really
    guarantees safe from the main thread. Under load (a live Speechmatics
    session running — mic + system-audio + asyncio threads all active) a
    close hung again despite this exact delay having worked in lower-thread-
    count demo-mode testing, consistent with that call executing off the
    main thread being the actually-unreliable part, not the delay length
    itself. AppHelper.callLater runs its callback through the Cocoa run
    loop on the main thread, same mechanism hide_from_dock() already uses
    for the same reason."""
    if HAS_APPKIT:
        AppHelper.callLater(delay, fn)
    else:
        threading.Timer(delay, fn).start()


# PIL's built-in load_default() bitmap font has no Cyrillic glyphs at all —
# it silently renders a .notdef box instead (found by actually looking at
# the rendered PNG, not by counting lit pixels like the earlier fix that
# introduced load_default(size=20): that fix made the box BIGGER and more
# visible, and was mistaken for a fixed letter — it was still the wrong
# glyph, just a more visible wrong glyph). These are real macOS system
# fonts, always present, and actually cover Cyrillic — first one found wins.
_CYRILLIC_FONT_CANDIDATES = (
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _load_label_font(size: int) -> ImageFont.ImageFont:
    for path in _CYRILLIC_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


# Menu-bar icon target size — macOS status items render at ~22pt, so 44px
# is the natural @2x size (matches every other icon in that bar, which are
# all Retina-rendered). Drawn at 4x that (176px) and downsampled with
# LANCZOS for antialiasing, then rebuilt from the alpha channel: PIL's
# ImageDraw has no antialiasing of its own — ellipse()/text() at the final
# 32px size drew hard, unantialiased pixel edges, which is what made the
# icon look chunky/pixelated next to every neighboring icon's smooth
# circles (found by comparing a real screenshot of the menu bar directly,
# not guessed).
_ICON_SIZE = 44
_SUPERSAMPLE = 4


def _make_icon_image(label: str) -> Image.Image:
    """Small dark circle with a single letter — generated, no asset file."""
    big = _SUPERSAMPLE * _ICON_SIZE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = _SUPERSAMPLE * 2
    draw.ellipse((margin, margin, big - margin, big - margin), fill=(40, 38, 46, 255))
    font = _load_label_font(int(big * 0.55))
    draw.text((big / 2, big / 2), label, fill=(255, 255, 255, 255), anchor="mm", font=font)
    return img.resize((_ICON_SIZE, _ICON_SIZE), Image.LANCZOS)


_REASSERT_DELAYS = (0.0, 0.1, 0.3, 0.6, 1.0, 2.0)


def hide_from_dock() -> None:
    """Hide the app from the Dock and Cmd+Tab, matching Type's "one-screen"
    menu-bar-only feel. Call from __main__, on the main thread, before
    webview.create_window()/webview.start().

    A single call here is NOT reliable on its own — confirmed empirically,
    including a real Objective-C swizzle attempt that hit infinite recursion
    (AppKit.NSApplication.setActivationPolicy_, captured as a Python
    reference before a Category patches it, still resolves to the PATCHED
    version at call time — PyObjC methods aren't frozen the way a plain
    Python function reference would be). pywebview's own cocoa.py forces
    Regular policy the first time its module loads (lazily, inside
    create_window()) — a single later call to set Accessory sometimes wins
    the race against that and sometimes doesn't, non-deterministically,
    across otherwise-identical runs of the same build (confirmed: two runs
    of one unchanged binary gave different results). Brute-force fix:
    reassert Accessory repeatedly over the first two seconds via
    AppHelper.callLater, instead of trying to win the race with one call."""
    if not HAS_APPKIT:
        return
    for delay in _REASSERT_DELAYS:
        AppHelper.callLater(
            delay,
            AppKit.NSApplication.sharedApplication().setActivationPolicy_,
            AppKit.NSApplicationActivationPolicyAccessory,
        )


def start_tray(window, label: str):
    """Create the menu-bar icon. Call from __main__, on the main thread,
    BEFORE webview.start() — webview.start() is what actually enters
    NSApplication.run() afterward and starts servicing the icon's clicks.

    window.hidden (pywebview's own attribute) only reflects the value passed
    to create_window() at construction time and is never updated by
    show()/hide() — so visibility is tracked locally here instead.

    Returns (icon, hide) — `hide` is exposed so the in-window "Свернуть"
    button can hide the window through the SAME state the tray menu toggles,
    instead of calling window.hide() directly and desyncing the two.
    """
    is_hidden = False

    def hide():
        nonlocal is_hidden
        window.hide()
        is_hidden = True

    def show():
        nonlocal is_hidden
        window.show()
        is_hidden = False

    def toggle(icon, item):
        show() if is_hidden else hide()

    def quit_app(icon, item):
        icon.stop()
        window.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("Показать/Скрыть", toggle, default=True),
        pystray.MenuItem("Выход", quit_app),
    )
    icon = pystray.Icon(f"daily-standup-{label}", _make_icon_image(label), menu=menu)
    icon.run_detached(setup=lambda icon: None)
    icon.visible = True
    return icon, hide


def start_layout_tray(window, layouts, order, state_ref, on_select):
    """Menu-bar icon for the unified app (run_app.py) — a submenu of
    layouts (radio-style, checkmark on the active one) above the same
    Показать/Скрыть + Выход pair start_tray already provides for the three
    standalone scripts. Same safety rules as start_tray (see its docstring):
    everything here runs on the main thread via run_detached, so a click
    handler can call window.resize()/window.hide()/window.show()/
    window.destroy() directly — no threading.Timer needed for THIS handler
    itself (unlike each run_*.py's exposed close_window, which runs on the
    JS-bridge thread instead and does need one).

    `on_select(key)` does the actual layout switch (resize/load_url/push
    the current meeting state into the new page) — this function only
    builds the menu and calls it on click; it has no idea what a layout
    switch actually does or what state.py/run_app.py's state shapes are.
    """
    is_hidden = False

    def hide():
        nonlocal is_hidden
        window.hide()
        is_hidden = True

    def show():
        nonlocal is_hidden
        window.show()
        is_hidden = False

    def toggle(icon, item):
        show() if is_hidden else hide()

    def quit_app(icon, item):
        icon.stop()
        window.destroy()

    def _select(key):
        def _handler(icon, item):
            on_select(key)
            icon.update_menu()

        return _handler

    def _checked(key):
        return lambda item: state_ref["layout"] == key

    layout_items = [
        pystray.MenuItem(layouts[key]["label"], _select(key), checked=_checked(key), radio=True)
        for key in order
    ]
    menu = pystray.Menu(
        *layout_items,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Показать/Скрыть", toggle, default=True),
        pystray.MenuItem("Выход", quit_app),
    )
    icon = pystray.Icon("daily-standup-app", _make_icon_image("Д"), menu=menu)
    icon.run_detached(setup=lambda icon: None)
    icon.visible = True
    return icon, hide
