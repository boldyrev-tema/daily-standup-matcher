#!/bin/bash
# Double-click debug launcher — Finder opens this in a visible Terminal
# window, so prints/errors are visible live. See "Второй экран.app" for the
# silent, no-terminal variant.
cd "/Users/tema/dev/daily_standup_matcher" || exit 1
venv/bin/python3.14 run_second_screen.py
