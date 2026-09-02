"""A MitID login as a Textual screen, for TUIs that need one.

The protocol reports itself through callbacks and draws nothing, so the same
login can be a few lines on stderr or a screen in an application. This is the
screen. It knows nothing about which service is being logged in to: hand it a
callable that performs the login and it renders whatever that callable narrates
on the way through.

    def log_in(user_id, **callbacks):
        return my_broker.log_in(session, START_URL, user_id, **callbacks)

    result = await self.push_screen_wait(MitIDLoginScreen(log_in))

`result` is whatever the callable returned, or None if the user gave up. Needs
the `textual` extra: pip install mitid-client[textual]
"""

from __future__ import annotations

import threading

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    LoadingIndicator,
    OptionList,
    Static,
)
from textual.worker import get_current_worker

# The MitID app scans a real QR, so the polarity has to hold whatever colour
# scheme the terminal is set to - hence literal black and white rather than the
# theme's own foreground and background.
DARK, LIGHT = "black", "white"
UPPER_HALF = "▀"  # foreground paints the top module, background the bottom
# qrcode draws one module of margin; the standard asks for four, and a scanner
# is much happier when it gets them.
QUIET_ZONE = 3


def qr_text(matrix: list[list[bool]], quiet_zone: int = QUIET_ZONE) -> Text:
    """Render a QR matrix as half-block characters, two module rows per line."""
    width = len(matrix[0]) + 2 * quiet_zone
    blank = [False] * width
    rows = (
        [blank] * quiet_zone
        + [[False] * quiet_zone + list(row) + [False] * quiet_zone for row in matrix]
        + [blank] * quiet_zone
    )
    if len(rows) % 2:  # an odd count would leave the last row with no bottom half
        rows.append(blank)

    rendered = Text(no_wrap=True)
    for index, (top, bottom) in enumerate(zip(rows[::2], rows[1::2])):
        if index:
            rendered.append("\n")
        for dark_top, dark_bottom in zip(top, bottom):
            style = f"{DARK if dark_top else LIGHT} on {DARK if dark_bottom else LIGHT}"
            rendered.append(UPPER_HALF, style=style)
    return rendered


class MitIDLoginScreen(Screen):
    """Runs one MitID login, showing whatever it has to say while it happens."""

    DEFAULT_CSS = """
    MitIDLoginScreen { align: center middle; }

    MitIDLoginScreen #mitid-box {
        width: 72;
        max-width: 100%;
        height: auto;
        max-height: 100%;
        padding: 1 3;
        border: thick $primary 60%;
        background: $surface;
    }

    MitIDLoginScreen .mitid-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
    }

    MitIDLoginScreen .mitid-service {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    MitIDLoginScreen #mitid-qr {
        width: 100%;
        height: auto;
        content-align: center middle;
        margin: 1 0;
    }

    MitIDLoginScreen #mitid-otp {
        width: 100%;
        height: auto;
        text-align: center;
        text-style: bold;
        color: $warning;
        margin: 1 0;
    }

    MitIDLoginScreen #mitid-status {
        width: 100%;
        text-align: center;
        color: $secondary;
        margin: 1 0;
    }

    MitIDLoginScreen #mitid-error {
        width: 100%;
        text-align: center;
        color: $error;
        margin: 1 0;
    }

    MitIDLoginScreen #mitid-loading { height: 1; }

    MitIDLoginScreen #mitid-prompt { height: auto; margin: 1 0; }
    MitIDLoginScreen #mitid-prompt Input { width: 1fr; }
    MitIDLoginScreen #mitid-prompt Button { width: auto; min-width: 10; margin-left: 1; }

    MitIDLoginScreen #mitid-choices { height: auto; max-height: 12; margin: 1 0; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        login,
        *,
        user_id: str = "",
        service: str = "",
        title: str = "MitID login",
    ) -> None:
        """`login(user_id, **callbacks)` performs the login and returns anything.

        Pass `user_id` if it is already known - otherwise the screen asks for
        it, which is the only thing about a login that cannot be guessed.
        `service` names who is asking, for the line above the QR; the protocol
        will say so itself once it connects, so it is only worth setting when
        the screen should say something before that.
        """
        super().__init__()
        self._login = login
        self._user_id = user_id
        self._service = service
        self._title = title
        # How the worker thread waits for something typed on the main thread.
        self._answered = threading.Event()
        self._answer: str = ""
        self._choice: int = -1

    # ── layout ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Center():
            with VerticalScroll(id="mitid-box"):
                yield Static(self._title, classes="mitid-title")
                yield Static(self._service, classes="mitid-service", id="mitid-service")
                yield Static("", id="mitid-qr")
                yield Static("", id="mitid-otp")
                yield LoadingIndicator(id="mitid-loading")
                yield Label("", id="mitid-status")
                yield Label("", id="mitid-error")
                with Horizontal(id="mitid-prompt"):
                    yield Input(id="mitid-input")
                    yield Button("OK", variant="primary", id="mitid-ok")
                yield OptionList(id="mitid-choices")
        yield Footer()

    def on_mount(self) -> None:
        for hidden in ("#mitid-qr", "#mitid-otp", "#mitid-prompt", "#mitid-choices",
                       "#mitid-error"):
            self.query_one(hidden).display = False
        if not self._service:
            self.query_one("#mitid-service").display = False
        self._run()

    # ── answering the worker ────────────────────────────────────────────

    @on(Button.Pressed, "#mitid-ok")
    @on(Input.Submitted, "#mitid-input")
    def _submit(self) -> None:
        field = self.query_one("#mitid-input", Input)
        self._answer = field.value.strip()
        field.value = ""
        self._answered.set()

    @on(OptionList.OptionSelected, "#mitid-choices")
    def _chose(self, event: OptionList.OptionSelected) -> None:
        self._choice = event.option_index
        self._answered.set()

    def action_cancel(self) -> None:
        # Release the worker if it is sitting on a prompt, so the thread ends
        # rather than blocking forever on an event nobody will ever set.
        self._answer, self._choice = "", -1
        self._answered.set()
        self.dismiss(None)

    # ── the login itself ────────────────────────────────────────────────

    @work(thread=True)
    def _run(self) -> None:
        worker = get_current_worker()
        call = self.app.call_from_thread

        def show(selector: str, visible: bool = True) -> None:
            call(setattr, self.query_one(selector), "display", visible)

        def on_status(message: str) -> None:
            if worker.is_cancelled:
                return
            # A status line under the QR would be painted over on the next
            # frame in a terminal; here it simply sits below it, so the QR can
            # stay up for as long as it is scannable.
            call(self.query_one("#mitid-status", Label).update, message)

        def on_qr(matrix: list[list[bool]]) -> None:
            if worker.is_cancelled:
                return
            call(self.query_one("#mitid-qr", Static).update, qr_text(matrix))
            show("#mitid-qr")

        def on_otp(code: str) -> None:
            if worker.is_cancelled:
                return
            # The app asks for a typed code or a scanned QR, never both, so
            # the QR comes down the moment a code arrives.
            show("#mitid-qr", False)
            spaced = " ".join(code)
            call(
                self.query_one("#mitid-otp", Static).update,
                f"Type this code in the MitID app\n{spaced}",
            )
            show("#mitid-otp")

        def ask(prompt: str, placeholder: str = "") -> str:
            if worker.is_cancelled:
                return ""
            self._answered.clear()
            call(self.query_one("#mitid-status", Label).update, prompt)
            field = self.query_one("#mitid-input", Input)
            call(setattr, field, "placeholder", placeholder or prompt)
            show("#mitid-prompt")
            call(field.focus)
            self._answered.wait()
            show("#mitid-prompt", False)
            return self._answer

        def choose(options: list[str]) -> int:
            if worker.is_cancelled:
                return 0
            self._answered.clear()
            call(
                self.query_one("#mitid-status", Label).update,
                "Your MitID unlocks more than one identity - pick one:",
            )
            chooser = self.query_one("#mitid-choices", OptionList)
            call(chooser.clear_options)
            call(chooser.add_options, options)
            show("#mitid-choices")
            call(chooser.focus)
            self._answered.wait()
            show("#mitid-choices", False)
            # A cancel releases the wait with -1; anything is safe to return
            # here because the screen is already on its way out.
            return max(self._choice, 0)

        user_id = self._user_id or ask("Your MitID user ID (not your CPR number):",
                                       "MitID user ID")
        if not user_id or worker.is_cancelled:
            return

        try:
            result = self._login(
                user_id,
                on_status=on_status,
                on_qr=on_qr,
                on_otp=on_otp,
                ask_token_code=ask,
                choose_identity=choose,
            )
        except Exception as error:  # noqa: BLE001 - the message is the point
            if not worker.is_cancelled:
                show("#mitid-qr", False)
                show("#mitid-otp", False)
                show("#mitid-loading", False)
                call(self.query_one("#mitid-error", Label).update, str(error))
                show("#mitid-error")
                call(self.query_one("#mitid-status", Label).update,
                     "Press escape to go back, or try again.")
            return

        if not worker.is_cancelled:
            call(self.dismiss, result)
