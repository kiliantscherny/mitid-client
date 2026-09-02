"""Two things in the vendored protocol code that this repository changed.

`core.py` and `srp.py` are kept close to upstream, so anything altered in them
is worth pinning down. The protocol itself cannot be tested without a real
MitID and a real phone; these two can.
"""

from __future__ import annotations

import inspect

from mitid.core import BrowserClient
from mitid.srp import pad, unpad

BLOCK_SIZE = 16


def test_no_shared_session_by_default():
    """Upstream builds one Session in the signature's default.

    That evaluates once at import, so every client made without an explicit
    session shares it. Every caller here passes one, so it only ever mattered
    latently, but the default is `None` now and the session is built per client.
    """
    parameters = inspect.signature(BrowserClient.__init__).parameters
    assert parameters["requests_session"].default is None


def test_padding_round_trips():
    """`pad` and `unpad` were lambdas here and are functions now."""
    for length in range(0, 40):
        message = "x" * length
        padded = pad(message)
        assert len(padded) % BLOCK_SIZE == 0
        # Padding always adds at least one byte, so a whole block is added to
        # something already the right length. Otherwise unpad could not tell.
        assert len(padded) > length
        assert unpad(padded) == message


def test_padding_uses_the_pkcs7_byte():
    """Each added byte says how many were added, which is what unpad reads."""
    padded = pad("abc")
    added = BLOCK_SIZE - 3
    assert padded[3:] == chr(added) * added
