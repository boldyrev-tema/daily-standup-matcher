"""py2app build script for the "Полоса" layout — same approach proven on the
"Колонка" layout (see setup_column.py for the full history of why py2app,
and why each `packages` entry below is needed).

Build: venv/bin/python3.14 setup_polosa_replay.py py2app
"""
import os

from setuptools import setup

APP = ["run_polosa_replay.py"]
DATA_FILES = [
    "polosa.html",
    ("fixtures", ["fixtures/sprint.json", "fixtures/sample_daily_transcript.json"]),
]
# Bundled only if present locally — see setup_app.py's comment for why.
if os.path.exists("bin/SystemAudioDump"):
    DATA_FILES.append(("bin", ["bin/SystemAudioDump"]))
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,
    "plist": {
        "CFBundleName": "Полоса",
        "CFBundleDisplayName": "Полоса",
        "CFBundleIdentifier": "ru.boldyrev.dailystandup.polosa",
        "CFBundleShortVersionString": "1.0",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    },
    # Same two data-only/native packages that needed forcing for Колонка —
    # see setup_column.py's comments for why (dictionary files and a
    # dlopen-from-zip failure respectively). run_polosa_replay.py imports
    # _apply_pending from run_second_screen, which pulls in the same
    # dependency set even though this layout has no --live path of its own.
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
