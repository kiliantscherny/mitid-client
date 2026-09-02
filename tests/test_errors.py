"""Turning MitID's error responses into something a person can act on.

The protocol reports failures by raising the server's raw body, which is a wall
of JSON with a perfectly good explanation buried in it. Getting that out is the
difference between "MitID said no" and knowing why.
"""

from __future__ import annotations

import json

from mitid import _explain

SPOKEN = {
    "userMessage": {
        "title": {"text": "Forkert bruger-id"},
        "text": {"text": "Prøv igen, eller nulstil dit MitID."},
    },
    "message": "user_not_found",
    "errorCode": "AUTH-014",
}


def test_prefers_what_the_real_client_would_have_shown():
    assert _explain(Exception(json.dumps(SPOKEN))) == (
        "Forkert bruger-id: Prøv igen, eller nulstil dit MitID."
    )


def test_reads_it_out_of_bytes_too():
    raw = json.dumps(SPOKEN).encode("utf-8")
    assert "Forkert bruger-id" in _explain(Exception(raw))


def test_falls_back_to_what_it_logs():
    logged = json.dumps({"message": "user_not_found"})
    assert _explain(Exception(logged)) == "user_not_found"
    assert _explain(Exception(json.dumps({"errorCode": "AUTH-014"}))) == "AUTH-014"


def test_a_plain_string_is_passed_through():
    assert _explain(Exception("the connection went away")) == "the connection went away"


def test_a_title_with_no_body_still_says_something():
    only_title = {"userMessage": {"title": {"text": "Spærret"}}}
    assert _explain(Exception(json.dumps(only_title))) == "Spærret"
