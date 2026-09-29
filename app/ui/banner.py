"""Terminal startup splash: the No_Loop mascot + status panel.

Pure functions only — nothing here prints (keeps T20 clean) and the output is
straightforward to unit-test. ``app.serve_ui`` owns writing and animation.

Mascot: a cybernetic torso (armour plates, chest reactor, console strip)
carrying an owl head that **rotates** — skull shifts left, centre, right while
the neck stays planted on the shoulders, exactly how an owl swivels.

The head and body are composed by centre-joining two independent blocks, so
editing one can never knock the other out of alignment.

The panel underneath is not decoration: it reports the URL, the data directory,
the event transport, the privacy posture and how to stop, so the very first
screen already answers "where is my data and how do I get out of this?".
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

__all__ = ["frames", "static", "head_frames", "supports_color", "mascot_width", "HEIGHT"]

# --- mascot -----------------------------------------------------------------

#: Skull turn in columns — centre, ease left, hold, ease back, centre, right.
#: A smooth swivel rather than a jump cut, so it reads as a head turning.
_TURNS: tuple[int, ...] = (0, -2, -3, -2, 0, 2, 3, 2)

#: The swivelling part of the head (everything above the neck).
#: Every row is the same width and internally symmetric, so centre-joining it
#: with the body cannot drift.
_SKULL = tuple(
    r"""
    /\                    /\
  /  \      __      /  \
  / /\ \    /  \    \ /\ /
| |  | |   | @@  @@ |   | |  | |
| |  | |   |  ____  |   | |  | |
| |  | |   | /    \ |   | |  | |
| |  | |   | \____/ |   | |  | |
\ \ / /        ||        / / \ \
\ V /         ||         / V \
|_|         /  \         |_|
""".strip("\n").splitlines()
)

#: Planted on the shoulders — never moves, otherwise the head looks detached.
_NECK = tuple(
    r"""
/____\
|__|  |__|
""".strip("\n").splitlines()
)

_BODY = tuple(
    r"""
          /              \
      / .------------------. \
    | .----------------------. |
    | |    |  [.]  [.]  |    | |
    |        ==========        |
    | |    N O _ L O O P     | |
    | '----------------------' |
    |____________||____________|
""".strip("\n").splitlines()
)

_SKULL_ROWS = len(_SKULL)
#: Total rendered rows — the animation rewinds the cursor by exactly this much.
HEIGHT = _SKULL_ROWS + len(_NECK) + len(_BODY)


def mascot_width() -> int:
    widest = max(len(line) for block in (_SKULL, _NECK, _BODY) for line in block)
    return widest + 4  # breathing room so the panel never clips the art


def _centre(line: str, width: int, shift: int = 0) -> str:
    """Place one art line on a fixed grid, honouring an optional turn."""
    stripped = line.strip()
    start = width // 2 - len(stripped) // 2 + shift
    start = max(0, min(width - len(stripped), start))
    return " " * start + stripped


def _rows(turn: int, width: int) -> list[str]:
    shift = _TURNS[turn % len(_TURNS)]
    skull = [_centre(line, width, shift) for line in _SKULL]
    neck = [_centre(line, width) for line in _NECK]
    body = [_centre(line, width) for line in _BODY]
    return skull + neck + body


# --- colour -----------------------------------------------------------------

_RESET = "\033[0m"
_STYLES = {
    "dim": "\033[2m",
    "bold": "\033[1m",
    "steel": "\033[36m",  # armour plating
    "gold": "\033[93m",  # eyes + reactor
    "green": "\033[92m",  # the URL
    "cyan": "\033[96m",
}


def _paint(text: str, style: str, *, color: bool) -> str:
    if not color or style not in _STYLES:
        return text
    return f"{_STYLES[style]}{text}{_RESET}"


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(text: str) -> str:
    """Text as it lands on screen — colour escapes removed, so widths are real."""
    return _ANSI.sub("", text)


def _mascot(rows: list[str], *, color: bool) -> str:
    painted: list[str] = []
    for index, row in enumerate(rows):
        if index < _SKULL_ROWS:
            # eye band and beak glow; the rest of the skull is bare metal
            style = "gold" if ("@@" in row or "\\____/" in row) else "steel"
        else:
            style = "gold" if "[.]" in row or "===========" in row else "steel"
        painted.append(_paint(row.rstrip(), style, color=color))
    return "\n".join(painted)


# --- status panel ------------------------------------------------------------


def _supports_unicode() -> bool:
    """Box-drawing only when the stream can actually encode it."""
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return encoding in {"utf-8", "utf8", "cp65001", "utf_8"}


def _panel(meta: dict[str, Any], *, color: bool) -> str:
    """Status block: how to reach it, where records live, and how to stop.

    Kept to eight rows on purpose — the whole splash has to fit a 30-row
    terminal so the art never scrolls out of view.
    """
    entries = [
        ("ui", str(meta.get("url", ""))),
        ("data", str(meta.get("data_dir", ""))),
        ("events", str(meta.get("events", "SSE push - no polling"))),
        ("privacy", str(meta.get("privacy", "nothing leaves this machine"))),
    ]
    label_w = max(len(k) for k, _ in entries)
    value_w = max(len(v) for _, v in entries)
    title = f"{meta.get('name', 'No_Loop')}  {meta.get('version', '')}".strip()
    # The key sequence rides along in the header instead of taking a row of its
    # own — knowing how to stop the app is the one thing that must stay visible.
    stop = str(meta.get("stop", "")).strip()
    if stop:
        title = f"{title} - {stop} to stop"
    # every row must fit inside the box, header rows included
    inner = max(label_w + 2 + value_w + 2, len(title) + 2)

    if _supports_unicode():
        top, mid, bot, vbar = ("┌", "├", "└", "│")
        top_rule, mid_rule, bot_rule = "┐", "┤", "┘"
        edge = "─"
    else:
        top = mid = bot = top_rule = mid_rule = bot_rule = "+"
        vbar, edge = "|", "-"

    def rule(left: str, right: str) -> str:
        return left + edge * inner + right

    def cell(text: str, style: str = "") -> str:
        body = f" {text} "
        body += " " * max(0, inner - len(body))
        return _paint(body, style, color=color)

    lines = [
        rule(top, top_rule),
        f"{vbar}{cell(title, 'bold')}{vbar}",
        rule(mid, mid_rule),
    ]
    for key, value in entries:
        lines.append(f"{vbar}{cell(f'{key.ljust(label_w)}  {value}')}{vbar}")
    lines.append(rule(bot, bot_rule))
    return "\n".join(lines)


def _frame_width(meta: dict[str, Any]) -> int:
    """Panel and art share one width, so the mascot sits centred in the card."""
    panel_width = max(
        (len(_strip(line)) for line in _panel(meta, color=False).splitlines()), default=0
    )
    return max(mascot_width(), panel_width)


def _compose(meta: dict[str, Any], *, color: bool, turn: int) -> str:
    art = _mascot(_rows(turn, _frame_width(meta)), color=color)
    return "\n".join([art, "", _panel(meta, color=color)])


def frames(meta: dict[str, Any], *, color: bool = True) -> list[str]:
    """One full splash per animation step (skull in each turn position)."""
    return [_compose(meta, color=color, turn=i) for i in range(len(_TURNS))]


def static(meta: dict[str, Any], *, color: bool = True) -> str:
    """Single non-animated splash — for pipes, logs, ``--no-banner`` off, CI."""
    return _compose(meta, color=color, turn=0)


def head_frames(meta: dict[str, Any], *, color: bool = True) -> list[str]:
    """Swivel frames for **just** the skull and neck.

    A full splash is ~40 rows, which will not hold still on a 30-row terminal,
    so the cursor-rewind animation would smear. The caller plays this shorter
    intro first, clears it, then prints the full static banner — every terminal
    gets the rotating owl, and nobody ends up staring at a half-scrolled card.
    """
    width = _frame_width(meta)
    out: list[str] = []
    for turn in range(len(_TURNS)):
        rows = [_centre(line, width, _TURNS[turn]) for line in _SKULL]
        rows += [_centre(line, width) for line in _NECK]
        out.append(_mascot(rows, color=color))
    return out


def supports_color(stream: Any = None) -> bool:
    """Colour only when the stream is a real terminal and NO_COLOR is unset."""
    target = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return bool(target.isatty())
    except Exception:  # noqa: BLE001 - an odd stream must never break startup
        return False
