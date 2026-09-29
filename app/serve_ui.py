r"""Launch the No_Loop local UI — single command:  python -m app.serve_ui

Prints the animated mascot splash (cybernetic torso + swivelling owl head),
binds 127.0.0.1 only (local-first; never network-exposed), then opens the
browser. Live updates are SSE-pushed, so the browser never polls and the API
is never overloaded.

  python -m app.serve_ui               splash + auto-open the browser
  python -m app.serve_ui --no-browser  headless / script-friendly
  python -m app.serve_ui --no-banner   plain one-liner (pipes, CI, logs)
  start.ps1                            creates the venv, then runs the above
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
import webbrowser
from pathlib import Path
from typing import IO, Any

from app.ui import banner
from app.ui.server import UILauncher, serve

#: Gap between swivel frames. Slow enough to read as a head turn, short enough
#: that the splash never feels like waiting for the app.
_FRAME_DELAY = 0.11

#: Status lines printed underneath the splash (they must fit too).
_FOOTER_LINES = 2

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_VERSION_KEY = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _version() -> str:
    """Installed metadata first, then the repo's pyproject, then honestly 'dev'."""
    try:
        from importlib.metadata import version

        return f"v{version('noloop')}"
    except Exception:  # noqa: BLE001, S110 - not installed is the normal local case
        pass
    try:
        text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return "dev"
    found = _VERSION_KEY.search(text)
    return f"v{found.group(1)}" if found else "dev"


def _visible_width(text: str) -> int:
    """Screen columns a frame occupies, ignoring ANSI colour escapes."""
    return max((len(_ANSI.sub("", line)) for line in text.splitlines()), default=0)


def _fits(frame: str) -> bool:
    """Animate only when the whole splash stays on one screen.

    If a line wraps, or the content scrolls, the cursor-rewind maths used by
    the animation would smear the screen — so in that case we print the static
    splash instead. Degraded, never broken.
    """
    columns, rows = shutil.get_terminal_size()
    lines = frame.splitlines()
    return columns >= _visible_width(frame) and rows >= len(lines) + _FOOTER_LINES + 1


def _animate(stream: IO[str], frames: list[str], delay: float) -> None:
    """Play the swivel, leaving the final frame on screen for the status lines."""
    height = len(frames[0].splitlines())
    rewind = f"\033[{height}A\033[J"  # up one frame, then clear to end of screen
    for index, frame in enumerate(frames):
        if index:
            stream.write(rewind)
        stream.write(frame)
        stream.write("\n")
        stream.flush()
        if index < len(frames) - 1:
            time.sleep(delay)


def _splash(stream: IO[str], meta: dict[str, Any], *, color: bool, animate: bool) -> None:
    full = banner.static(meta, color=color)
    try:
        if animate:
            if _fits(full):
                _animate(stream, banner.frames(meta, color=color), _FRAME_DELAY)
                return
            # Too short to hold the whole splash still: play the swivel on just
            # the skull+neck, then rewind it so the full banner replaces it.
            heads = banner.head_frames(meta, color=color)
            if heads and all(_fits(head) for head in heads):
                height = len(heads[0].splitlines())
                _animate(stream, heads, _FRAME_DELAY)
                stream.write(f"\033[{height}A\033[J")
                stream.flush()
        stream.write(full)
        stream.write("\n")
        stream.flush()
    except (UnicodeEncodeError, OSError):
        # Never let a console encoding problem stop the app from starting.
        stream.write(banner.static(meta, color=False).encode("ascii", "replace").decode())
        stream.write("\n")
        stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser(prog="noloop-ui", description="Start the No_Loop local UI")
    parser.add_argument("--data-dir", default=".local-data", help="where local records are stored")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not auto-open the browser")
    parser.add_argument("--no-banner", action="store_true", help="print the plain one-liner only")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    args = parser.parse_args()

    url = f"http://127.0.0.1:{args.port}"
    meta: dict[str, Any] = {
        "name": "No_Loop",
        "version": _version(),
        "url": url,
        "data_dir": args.data_dir,
        "events": "SSE push - no polling",
        "privacy": "local-only - nothing leaves this machine",
        "stop": "Ctrl+C",
        "tagline": "local-first job application center",
    }

    if args.no_banner:
        sys.stdout.write(f"No_Loop {_version()} running at {url}  (Ctrl+C to stop)\n")
        sys.stdout.flush()
    else:
        color = (not args.no_color) and banner.supports_color(sys.stdout)
        _splash(sys.stdout, meta, color=color, animate=True)

    started = time.perf_counter()
    launcher = UILauncher(data_dir=args.data_dir, port=args.port)
    server = serve(launcher)
    elapsed = time.perf_counter() - started
    sys.stdout.write(f"  ready in {elapsed:.2f}s - serving {url}\n")
    sys.stdout.flush()

    if not args.no_browser:
        webbrowser.open(url)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        sys.stdout.write("\nstopping...\n")
        sys.stdout.flush()
        server.shutdown()


if __name__ == "__main__":
    main()
