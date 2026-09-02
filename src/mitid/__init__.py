"""Drive a MitID authentication session to an authorisation code.

Every MitID-protected site works the same way: its identity broker hands the
browser an `aux` blob, the browser feeds that to MitID's own JavaScript core
client, and the core client hands back an authorisation code the broker
exchanges for an identity. `authenticate` is the middle step - it takes the
`aux` a broker gave us and returns that code.

Which broker produced the aux is none of this module's business. See
nemlogin.py for the NemLog-in half of the dance.
"""

from __future__ import annotations

import base64
import binascii
import json

from mitid.core import BrowserClient

APP = "APP"
TOKEN = "TOKEN"


class MitIDError(Exception):
    """Raised when a MitID authentication cannot be completed."""


def authenticate(
    session,
    aux: dict,
    user_id: str,
    *,
    method: str = APP,
    password: str | None = None,
    ask_token_code=None,
    on_status=None,
    on_qr=None,
    on_otp=None,
) -> str:
    """Authenticate as `user_id` and return a MitID authorisation code.

    `aux` is the decoded blob from the broker. `method` is APP (approve in the
    MitID app) or TOKEN (six digits from a code token, followed by the account
    password). `ask_token_code` is called to collect those digits.

    The callbacks are how the user finds out what is happening: `on_status` for
    progress, `on_qr` with a QR matrix to render, `on_otp` with a code to type
    into the app.
    """
    checksum = aux["coreClient"]["checksum"]
    client_hash = binascii.hexlify(base64.b64decode(checksum)).decode("ascii")
    session_id = aux["parameters"]["authenticationSessionId"]

    client = BrowserClient(
        client_hash,
        session_id,
        session,
        on_qr_display=on_qr,
        on_status=on_status,
        on_otp=on_otp,
    )

    # The protocol code below reports failures by raising the server's raw
    # response body, which is a wall of JSON. MitID writes a perfectly good
    # explanation inside it, so unwrap that rather than passing the wall on.
    try:
        available = client.identify_as_user_and_get_available_authenticators(user_id)

        # MitID decides what a given user may authenticate with, so a method
        # that is merely configured on our side is not necessarily one they
        # can use.
        if method not in available:
            offered = ", ".join(sorted(available)) or "none"
            raise MitIDError(
                f"{user_id} cannot log in with {method} - MitID offers: {offered}"
            )

        if method == APP:
            client.authenticate_with_app()
        elif method == TOKEN:
            digits = (ask_token_code or input)("Six digits from your code token:")
            client.authenticate_with_token(digits.strip())
            if not password:
                raise MitIDError("the code token method also needs your MitID password")
            client.authenticate_with_password(password)
        else:
            raise MitIDError(f"unknown MitID method {method!r}")

        return client.finalize_authentication_and_get_authorization_code()
    except MitIDError:
        raise
    except Exception as error:
        raise MitIDError(_explain(error)) from error


def _explain(error: Exception) -> str:
    """Dig the human-readable half out of a MitID error response."""
    detail = error.args[0] if error.args else error
    if isinstance(detail, bytes):
        detail = detail.decode("utf-8", "replace")
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except ValueError:
            return detail.strip() or str(error)
    if not isinstance(detail, dict):
        return str(error)

    # userMessage is what the real client would have put on screen; message and
    # errorCode are what it logs. Prefer the one written for a person.
    spoken = detail.get("userMessage") or {}
    title = (spoken.get("title") or {}).get("text", "")
    body = (spoken.get("text") or {}).get("text", "")
    written = ": ".join(part for part in (title, body) if part)
    return written or detail.get("message") or detail.get("errorCode") or str(detail)
