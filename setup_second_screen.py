"""py2app build script for the "Второй экран" layout — same approach proven
on the "Колонка" layout (see setup_column.py for the full history of why
py2app, and why each `packages` entry below is needed).

Build: venv/bin/python3.14 setup_second_screen.py py2app
"""
from setuptools import setup

APP = ["run_second_screen.py"]
DATA_FILES = [
    "second_screen.html",
    ("fixtures", ["fixtures/sprint.json", "fixtures/sample_daily_transcript.json"]),
]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,
    "plist": {
        "CFBundleName": "Второй экран",
        "CFBundleDisplayName": "Второй экран",
        "CFBundleIdentifier": "ru.boldyrev.dailystandup.secondscreen",
        "CFBundleShortVersionString": "1.0",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Нужен для распознавания речи на дейлике (--live).",
    },
    # Same two data-only/native packages that needed forcing for Колонка —
    # see setup_column.py's comments for why (dictionary files and a
    # dlopen-from-zip failure respectively). This layout pulls in the same
    # dependencies (pymorphy3 via match_core, sounddevice via live_audio).
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
