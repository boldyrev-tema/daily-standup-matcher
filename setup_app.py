"""py2app build script for the unified app (run_app.py) — one process, live
choice of layout inside the product. Same recipe proven on setup_column.py
(see that file for the full history of why py2app, and why each `packages`
entry below is needed).

Unlike the three single-layout setup_*.py scripts, this one bundles all
three HTML templates — the unified app can end up on any layout. The
post-daily recap is rendered inline inside second_screen.html itself (no
separate template to bundle), same as run_second_screen.py's own build.

Build: venv/bin/python3.14 make_app_icon.py && venv/bin/python3.14 setup_app.py py2app
"""
import os

from setuptools import setup

if not os.path.exists("AppIcon.icns"):
    raise SystemExit("AppIcon.icns missing — run: venv/bin/python3.14 make_app_icon.py")

APP = ["run_app.py"]
DATA_FILES = [
    "second_screen.html",
    "column.html",
    "polosa.html",
    ("fixtures", ["fixtures/sprint.json", "fixtures/sample_daily_transcript.json"]),
]
# Committed in the repo (GPLv3, see bin/README.md), guarded on existence
# only so a build still succeeds (mic-only) if someone deletes bin/ locally.
if os.path.exists("bin/SystemAudioDump"):
    DATA_FILES.append(("bin", ["bin/SystemAudioDump"]))
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "AppIcon.icns",
    "plist": {
        "CFBundleName": "Дейлик",
        "CFBundleDisplayName": "Дейлик",
        "CFBundleIdentifier": "ru.boldyrev.dailystandup.app",
        "CFBundleShortVersionString": "1.0",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Нужен для распознавания речи на дейлике (--live).",
    },
    # Same two data-only/native packages that needed forcing for Колонка —
    # see setup_column.py's comments for why (dictionary files and a
    # dlopen-from-zip failure respectively).
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
