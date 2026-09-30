"""Startup entry point: version, frame sizing, and the splash's three paths.

The ANSI gate deserves its own test file because getting it wrong is silent in
both directions: answer ``False`` on a real console and the animated banner
simply never plays (nobody reports a missing animation, they just never see
it); answer ``True`` on a pipe and the escape codes end up in a log file. The
``False`` side is asserted here; the ``True`` side was verified by launching a
process against a live console, which no unit test can arrange.

Terminal sizes below are chosen around the real splash: ~29 lines wide enough
for the full card, ~12 for the skull-and-neck intro.
"""

from __future__ import annotations

import io
import shutil
from typing import Any

import pytest
from app import serve_ui

META: dict[str, Any] = {
    "name": "No_Loop",
    "version": "v0.1.0",
    "url": "http://127.0.0.1:8765",
    "data_dir": ".local-data",
    "events": "SSE push - no polling",
    "privacy": "nothing leaves this machine",
    "stop": "Ctrl+C",
}

#: (columns, rows) tall enough for the whole card + status line.
_BIG = (200, 60)
#: too short for the card, but tall enough for the skull-and-neck intro.
_SHORT = (200, 30)
#: too short for the intro as well — must fall back to plain text.
_TINY = (200, 10)


def _terminal(monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]) -> None:
    monkeypatch.setattr(shutil, "get_terminal_size", lambda: size)


def _splash(monkeypatch: pytest.MonkeyPatch, size: tuple[int, int], *, animate: bool) -> str:
    _terminal(monkeypatch, size)
    monkeypatch.setattr(serve_ui, "_FRAME_DELAY", 0)  # never sleep in a test
    buffer = io.StringIO()
    serve_ui._splash(buffer, META, color=False, animate=animate)
    return buffer.getvalue()


def test_version_is_prefixed_and_not_bare() -> None:
    version = serve_ui._version()
    assert version.startswith("v"), version
    assert version != "v"  # a missing version must read as "dev", never as ""


def test_visible_width_counts_columns_not_bytes() -> None:
    assert serve_ui._visible_width("abc\ndefgh") == 5  # the longest line wins
    assert serve_ui._visible_width("") == 0


def test_visible_width_ignores_colour_escapes() -> None:
    plain = "No_Loop"
    painted = f"\x1b[1m{plain}\x1b[0m"
    assert serve_ui._visible_width(painted) == len(plain)


def test_fits_rejects_a_screen_that_would_scroll(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = "\n".join(["x" * 40] * 20)
    # 20 lines + status line + spare row
    _terminal(monkeypatch, (80, 22))
    assert serve_ui._fits(frame) is True
    _terminal(monkeypatch, (80, 21))
    assert serve_ui._fits(frame) is False


def test_fits_rejects_a_frame_wider_than_the_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = "\n".join(["x" * 60] * 5)
    _terminal(monkeypatch, (59, 40))
    assert serve_ui._fits(frame) is False
    _terminal(monkeypatch, (60, 40))
    assert serve_ui._fits(frame) is True


def test_console_gate_reports_a_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never raise, and never hand a non-bool back to the caller as a decision."""
    monkeypatch.setattr(serve_ui.shutil, "get_terminal_size", lambda: (80, 24))
    assert isinstance(serve_ui._console_honours_ansi(), bool)


def test_static_splash_is_plain_text_and_carries_the_basics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = _splash(monkeypatch, _TINY, animate=False)
    assert "\x1b[" not in out, "a non-animated splash must never emit escapes"
    assert META["url"] in out
    assert META["data_dir"] in out
    assert "Ctrl+C" in out


def test_tall_terminal_gets_the_full_swivel(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _splash(monkeypatch, _BIG, animate=True)
    assert "\x1b[" in out, "a tall enough terminal should animate"
    assert "\x1b[J" in out, "each frame must clear before the redraw"
    assert META["url"] in out, "the finished card must be left on screen"


def test_short_terminal_rewinds_the_intro_then_prints_the_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = _splash(monkeypatch, _SHORT, animate=True)
    assert "\x1b[" in out, "the owl should still turn on a short terminal"
    assert META["url"] in out, "the intro must be replaced by the full card"


def test_tiny_terminal_degrades_to_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """The safety net: cursor moves in a screen that cannot host them smear."""
    out = _splash(monkeypatch, _TINY, animate=True)
    assert "\x1b[" not in out
    assert META["url"] in out, "degraded still means the banner is shown"


def test_the_ansi_gate_and_the_splash_agree(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whatever the gate decides, main() must never write escapes to a pipe.

    ``main`` picks ``animate`` from the gate, so a gate saying "no" has to be
    enough to keep every frame out of redirected output.
    """
    _terminal(monkeypatch, _BIG)
    gate = serve_ui._console_honours_ansi()
    if gate:
        pytest.skip("running attached to a real console")
    out = _splash(monkeypatch, _BIG, animate=gate)
    assert "\x1b[" not in out
