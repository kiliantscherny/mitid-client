"""Show a MitID login in a terminal: status lines, a scannable QR, a code box.

Everything here writes to stderr, so a run can still be piped somewhere useful
while the login is happening on screen.
"""

from __future__ import annotations

import sys
import threading

# The MitID app scans a real QR, so the polarity has to be right no matter what
# colour scheme the terminal happens to use - hence explicit black and white
# rather than the terminal's own foreground and background.
DARK_FG, LIGHT_FG = "\033[30m", "\033[97m"
DARK_BG, LIGHT_BG = "\033[40m", "\033[107m"
RESET = "\033[0m"
UPPER_HALF = "▀"  # foreground paints the top module, background the bottom
# qrcode already draws one module of margin; the standard asks for four.
QUIET_ZONE = 3


class LoginConsole:
    """Renders login progress, redrawing the QR frames in place.

    MitID sends its QR as two alternating frames a second apart, and the frames
    arrive on a background thread while the main thread prints status lines. One
    lock covers both so the two never interleave mid-redraw.
    """

    def __init__(self, stream=sys.stderr) -> None:
        self.stream = stream
        self.lock = threading.Lock()
        self.qr_lines = 0  # height of the QR block currently on screen

    @property
    def interactive(self) -> bool:
        return self.stream.isatty()

    def status(self, message: str) -> None:
        with self.lock:
            # Anything printed under a QR would be overwritten by the next
            # frame, so give up the drawing position and let the QR redraw
            # itself below the message.
            self._leave_qr()
            print(f"  {message}", file=self.stream, flush=True)

    def otp(self, code: str) -> None:
        with self.lock:
            self._leave_qr()
            spaced = " ".join(code)
            print(
                f"\n  Type this code in the MitID app:  \033[1m{spaced}{RESET}\n",
                file=self.stream,
                flush=True,
            )

    def qr(self, matrix: list[list[bool]]) -> None:
        """Draw one QR frame, replacing the previous one where possible."""
        lines = _render(matrix)
        with self.lock:
            if not self.interactive:
                # Redrawing needs a cursor. In a pipe or a log, one frame is
                # all we can honestly offer - both frames encode the same
                # challenge, so a scan of either still works.
                if self.qr_lines:
                    return
                print("\n".join(lines), file=self.stream, flush=True)
                self.qr_lines = len(lines)
                return

            if self.qr_lines:
                print(f"\033[{self.qr_lines}A", end="", file=self.stream)
            print("\n".join(lines), file=self.stream, flush=True)
            self.qr_lines = len(lines)

    def ask(self, prompt: str) -> str:
        with self.lock:
            self._leave_qr()
        print(f"  {prompt} ", end="", file=self.stream, flush=True)
        return input()

    def choose(self, options: list[str]) -> int:
        """Let the user pick one of several MitID identities."""
        with self.lock:
            self._leave_qr()
        print("\n  Your MitID unlocks more than one identity:", file=self.stream)
        for number, label in enumerate(options, start=1):
            print(f"    {number}. {label}", file=self.stream)
        while True:
            print("  Which one? ", end="", file=self.stream, flush=True)
            answer = input().strip()
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1
            print("  Pick one of the numbers above.", file=self.stream)

    def _leave_qr(self) -> None:
        """Stop treating the last QR as redrawable; caller holds the lock."""
        self.qr_lines = 0


def _render(matrix: list[list[bool]]) -> list[str]:
    """Turn a QR matrix into half-block lines, two module rows per line."""
    width = len(matrix[0]) + 2 * QUIET_ZONE
    blank = [False] * width
    rows = (
        [blank] * QUIET_ZONE
        + [[False] * QUIET_ZONE + list(row) + [False] * QUIET_ZONE for row in matrix]
        + [blank] * QUIET_ZONE
    )
    # An odd number of rows would leave the last one with no bottom half.
    if len(rows) % 2:
        rows.append(blank)

    lines = []
    # strict: the padding above makes the count even, and every row is the
    # same width. A QR drawn from mismatched halves is not worth rendering.
    for top, bottom in zip(rows[::2], rows[1::2], strict=True):
        cells = [
            (DARK_FG if dark_top else LIGHT_FG)
            + (DARK_BG if dark_bottom else LIGHT_BG)
            + UPPER_HALF
            for dark_top, dark_bottom in zip(top, bottom, strict=True)
        ]
        lines.append("  " + "".join(cells) + RESET)
    return lines
