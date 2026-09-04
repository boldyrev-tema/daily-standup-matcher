"""py2app build script for the "Колонка" layout — proof of concept before
extending to the other two layouts. Bundles a private copy of the
interpreter, so unlike the hand-rolled .app wrapper it does NOT re-exec into
Homebrew's shared Python.app (that re-exec was the actual, unfixable-from-
outside reason the Dock icon persisted — see the project memory entry dated
2 сен for the three failed workarounds).

Build: venv/bin/python3.14 setup_column.py py2app
"""
import os

from setuptools import setup

APP = ["run_column.py"]
DATA_FILES = [
    "column.html",
    ("fixtures", ["fixtures/sprint.json", "fixtures/sample_daily_transcript.json"]),
]
# Committed in the repo (GPLv3, see bin/README.md), guarded on existence
# only so a build still succeeds (mic-only) if someone deletes bin/ locally.
if os.path.exists("bin/SystemAudioDump"):
    DATA_FILES.append(("bin", ["bin/SystemAudioDump"]))
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,
    "plist": {
        "CFBundleName": "Колонка",
        "CFBundleDisplayName": "Колонка",
        "CFBundleIdentifier": "ru.boldyrev.dailystandup.column",
        "CFBundleShortVersionString": "1.0",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    },
    # pymorphy3_dicts_ru is a data-only package (dictionary files, almost no
    # code) — py2app's static import analysis bundles code fine but misses
    # its data directory, causing a "Can't find a dictionary for language
    # 'ru'" crash at runtime (confirmed empirically by running the built
    # binary directly). Listing it in packages forces the whole directory,
    # data included, to be copied in.
    # sounddevice ships a native PortAudio .dylib — py2app's default zipping
    # of site-packages breaks it (dlopen can't load a shared library out of
    # a zip archive; confirmed empirically: "OSError: cannot load library
    # '.../python314.zip/_sounddevice_data/.../libportaudio.dylib'"). The
    # dylib actually lives in a SEPARATE top-level package, `_sounddevice_data`
    # — `sounddevice` itself is just a flat .py module, not a package, so
    # listing only "sounddevice" here did nothing (confirmed: identical
    # failure after adding it alone). `_sounddevice_data` is the one that
    # needs to be a real, unzipped directory.
    "packages": [
        "pystray", "PIL", "webview", "AppKit", "Foundation", "objc",
        "pymorphy3_dicts_ru", "_sounddevice_data",
    ],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
