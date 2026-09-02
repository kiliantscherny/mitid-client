"""Rendering a QR the MitID app can actually read.

Both renderers pack two module rows into one line of half blocks, so a matrix
of N rows becomes ceil(N/2) lines plus the quiet zone. Polarity is the thing
that matters and the thing a refactor breaks: dark modules have to stay dark
whatever colour scheme the terminal is set to, or the app will not scan it.
"""

from __future__ import annotations

from mitid.ui import console
from mitid.ui.tui import DARK, LIGHT, qr_text

# A 3x3 matrix, which is odd on purpose: the last row has no partner and the
# renderers have to invent a blank one rather than dropping it.
MATRIX = [
    [True, False, True],
    [False, True, False],
    [True, True, False],
]


def test_console_render_shape():
    lines = console._render(MATRIX)
    height = 3 + 2 * console.QUIET_ZONE  # 3 modules plus the margin
    assert len(lines) == (height + 1) // 2
    assert all(console.UPPER_HALF in line for line in lines)


def test_console_keeps_the_polarity_explicit():
    """Never the terminal's own colours - a light-on-dark theme would invert it."""
    rendered = "".join(console._render(MATRIX))
    assert console.DARK_FG in rendered and console.LIGHT_FG in rendered
    assert console.DARK_BG in rendered and console.LIGHT_BG in rendered


def test_qr_text_shape_and_quiet_zone():
    text = qr_text(MATRIX, quiet_zone=2)
    lines = text.plain.splitlines()
    height = 3 + 2 * 2
    assert len(lines) == (height + 1) // 2
    assert all(len(line) == 3 + 2 * 2 for line in lines)


def test_qr_text_paints_black_and_white_not_theme_colours():
    text = qr_text(MATRIX, quiet_zone=1)
    styles = {str(span.style) for span in text.spans}
    assert styles <= {
        f"{DARK} on {DARK}",
        f"{DARK} on {LIGHT}",
        f"{LIGHT} on {DARK}",
        f"{LIGHT} on {LIGHT}",
    }
    # The corner of the quiet zone is light on light, and the matrix has at
    # least one dark module, so both extremes must be present.
    assert f"{LIGHT} on {LIGHT}" in styles
    assert any(style.startswith(DARK) for style in styles)


def test_a_quiet_zone_is_actually_drawn():
    """qrcode draws one module of margin; scanners want four."""
    lines = qr_text(MATRIX, quiet_zone=3).plain.splitlines()
    assert len(lines[0]) == 3 + 2 * 3
