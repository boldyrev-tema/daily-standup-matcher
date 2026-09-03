"""Patches a real upstream bug in pywebview's internal HTTP server (bottle
route `asset(file)` has no default for `file`, but is ALSO registered on the
bare `/` route, which calls it with zero arguments — crashes with
"TypeError: asset() missing 1 required positional argument: 'file'" whenever
anything requests the server's root URL instead of a specific filename).
Confirmed via a real crash — a live window went visually broken after this
exact traceback (2/3 сен), reproduced directly by curling the server's root
URL. Fixed upstream? Not as of pywebview 6.2.1 (checked via pip changelog +
a GitHub issue search — no matching fix found).

Idempotent: safe to run again after a `pip install --upgrade`. Run once
after `pip install -r requirements.txt`:

    venv/bin/python3.14 patch_pywebview.py
"""
from pathlib import Path

import webview

TARGET = Path(webview.__file__).parent / "http.py"
OLD = "            def asset(file):"
NEW = "            def asset(file=''):"


def main():
    text = TARGET.read_text()
    if NEW in text:
        print(f"already patched: {TARGET}")
        return
    if OLD not in text:
        raise SystemExit(
            f"expected line not found in {TARGET} — pywebview's internal "
            "http.py changed shape; re-check whether this bug is still "
            "present (and this patch still needed) before adjusting the "
            "match pattern."
        )
    TARGET.write_text(text.replace(OLD, NEW, 1))
    print(f"patched: {TARGET}")


if __name__ == "__main__":
    main()
