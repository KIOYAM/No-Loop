"""Startup banner: layout invariants, the swivel contract, and colour gating.

The mascot is hand-authored ASCII, so the things that can silently rot are
alignment, the head/body split the animation depends on, and the splash
overflowing a default terminal. These tests pin all three down.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from app.ui import banner

META: dict[str, Any] = {
    "name": "No_Loop",
    "version": "v0.1.0",
    "url": "http://127.0.0.1:8765",
    "data_dir": ".local-data",
    "events": "SSE push - no polling",
    "privacy": "nothing leaves this machine",
    "stop": "Ctrl+C",
}

#: Windows Terminal's default profile height. The splash has to hold still
#: here, or the ear tufts scroll out of view before anyone sees them.
DEFAULT_TERMINAL_ROWS = 30

#: Status line the launcher prints underneath the splash.
_FOOTER_LINES = 1


class _Tty(io.StringIO):
    def isatty(self) -> bool:  # noqa: D102 - behaviour switch for supports_color
        return True


def _centre_of(row: str) -> float:
    """Column index of a row's visual centre, leading pad included."""
    start = len(row) - len(row.lstrip())
    return start + (len(row.strip()) - 1) / 2


def test_height_is_the_sum_of_the_art_blocks() -> None:
    assert len(banner._SKULL) + len(banner._NECK) + len(banner._BODY) == banner.HEIGHT


def test_every_art_row_shares_one_centre() -> None:
    """A half-column drift is invisible per row and glaring once stacked."""
    centres = {_centre_of(row) for row in banner._rows(0, banner.mascot_width())}
    assert centres == {(banner.mascot_width() - 1) / 2}


def test_art_is_centred_inside_the_status_card() -> None:
    """The card sets the width, so the mascot needs equal margins either side."""
    lines = banner.static(META, color=False).splitlines()
    art = lines[: banner.HEIGHT]
    panel = lines[banner.HEIGHT + 1 :]

    panel_width = max(len(line) for line in panel)
    left = min(len(line) - len(line.lstrip()) for line in art)
    right = max(len(line.rstrip()) for line in art)

    assert left == panel_width - right, (left, panel_width - right)
    assert left > 0, "mascot should not sit flush against the card edge"


def test_splash_fits_a_default_terminal() -> None:
    lines = banner.static(META, color=False).splitlines()
    assert len(lines) + _FOOTER_LINES <= DEFAULT_TERMINAL_ROWS, len(lines)


def test_frames_all_stay_the_same_height() -> None:
    frames = banner.frames(META, color=False)
    assert len(frames) == len(banner._TURNS)
    heights = {len(frame.splitlines()) for frame in frames}
    assert len(heights) == 1
    assert heights.pop() == banner.HEIGHT + 1 + _panel_rows(META)


def _panel_rows(meta: dict[str, Any]) -> int:
    return len(banner._panel(meta, color=False).splitlines())


def test_skull_swivels_while_the_neck_and_body_stay_planted() -> None:
    """The rotation illusion: only the head block may move between frames."""
    anchored = banner.frames(META, color=False)[0].splitlines()
    skull_rows = len(banner._SKULL)

    for turn, shift in enumerate(banner._TURNS):
        if shift == 0:
            continue
        moving = banner.frames(META, color=False)[turn].splitlines()
        assert moving[:skull_rows] != anchored[:skull_rows], f"turn {turn} did not move"
        assert moving[skull_rows : banner.HEIGHT] == anchored[skull_rows : banner.HEIGHT], (
            f"turn {turn} dragged the neck or body with it"
        )


def test_head_frames_are_the_swivel_without_the_body() -> None:
    heads = banner.head_frames(META, color=False)
    assert len(heads) == len(banner._TURNS)
    assert all(len(head.splitlines()) == len(banner._SKULL) + len(banner._NECK) for head in heads)
    assert all("N O _ L O O P" not in head for head in heads), "body leaked into the intro"
    # and they really do turn
    first = heads[0].splitlines()[: len(banner._SKULL)]
    assert any(heads[6].splitlines()[: len(banner._SKULL)][i] != row for i, row in enumerate(first))


def test_head_intro_is_shorter_than_the_full_splash() -> None:
    """Otherwise the short-terminal fallback could never fit either."""
    head = len(banner.head_frames(META, color=False)[0].splitlines())
    full = len(banner.static(META, color=False).splitlines())
    assert head < full


def test_panel_reports_where_it_listens_and_how_to_stop() -> None:
    text = banner.static(META, color=False)
    for expected in (META["url"], META["data_dir"], META["privacy"], "Ctrl+C"):
        assert expected in text, expected


def test_panel_follows_the_supplied_metadata() -> None:
    overrides = {**META, "url": "http://127.0.0.1:9001", "data_dir": "records-elsewhere"}
    text = banner.static(overrides, color=False)
    assert "http://127.0.0.1:9001" in text
    assert "records-elsewhere" in text


def test_no_ansi_escapes_when_colour_is_off() -> None:
    assert "\x1b[" not in banner.static(META, color=False)
    assert all("\x1b[" not in frame for frame in banner.frames(META, color=False))
    assert all("\x1b[" not in head for head in banner.head_frames(META, color=False))


def test_colour_is_emitted_only_when_asked_for() -> None:
    assert "\x1b[" in banner.static(META, color=True)


def test_supports_color_refuses_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert banner.supports_color(_Tty()) is False


def test_supports_color_refuses_a_dumb_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert banner.supports_color(_Tty()) is False


def test_supports_color_refuses_a_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    assert banner.supports_color(io.StringIO()) is False


def test_supports_color_accepts_a_real_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    assert banner.supports_color(_Tty()) is True


def test_a_broken_stream_never_breaks_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Colour detection must degrade, not raise, on an unusual stream."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)

    class Explodes:
        def isatty(self) -> bool:
            raise OSError("no idea what I am")

    assert banner.supports_color(Explodes()) is False


def test_static_is_pure_ascii_without_colour(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipes and Windows code pages must not be fed box-drawing characters."""
    monkeypatch.setattr(banner, "_supports_unicode", lambda: False)
    banner.static(META, color=False).encode("ascii")
