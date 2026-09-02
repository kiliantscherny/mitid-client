"""The cookie store, which is the only thing here that touches the disk.

A login costs a tap on a phone, so a store that loses a session is worse than
no store at all - and what it writes is a live credential, so the file mode
matters as much as the round trip.
"""

from __future__ import annotations

import json
import stat
from datetime import datetime, timedelta

import pytest
import requests

from mitid.store import CookieStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return CookieStore("testapp", "service-session.json")


def _session_with(**cookies) -> requests.Session:
    session = requests.Session()
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="example.dk", path="/")
    return session


class _WrappedCookies:
    """A cookie container shaped the way curl_cffi shapes one.

    curl_cffi wraps a real cookiejar and iterates the *names* in it, so a
    caller reading `.name` off what iteration yields gets a string. Only the
    two things the store touches are modelled here, which is the whole point:
    the store should not need curl_cffi installed to be correct about it.
    """

    def __init__(self, jar) -> None:
        self.jar = jar

    def __iter__(self):
        return iter(cookie.name for cookie in self.jar)


class _WrappedSession:
    def __init__(self, session) -> None:
        self.cookies = _WrappedCookies(session.cookies)


def test_path_follows_xdg(store, tmp_path):
    assert store.path == tmp_path / "testapp" / "service-session.json"


def test_a_saved_session_comes_back(store):
    store.save(_session_with(JSESSIONID="abc", other="def"), user_id="SomeUser")

    restored = store.restore()
    assert restored is not None
    session, saved = restored
    assert dict(session.cookies) == {"JSESSIONID": "abc", "other": "def"}
    # Whatever the caller passed as extra comes back beside the cookies.
    assert saved["user_id"] == "SomeUser"
    assert saved["saved_at"]


def test_the_file_is_readable_by_nobody_else(store):
    path = store.save(_session_with(JSESSIONID="abc"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    # A looser mode left by an older version is tightened on the next write.
    path.chmod(0o644)
    store.save(_session_with(JSESSIONID="abc"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_session_that_hides_its_jar_is_saved_in_full(store):
    """A curl_cffi-shaped session round-trips with its cookies intact.

    Reaching for curl_cffi is what a caller does when the service fingerprints
    the TLS handshake, which is exactly the sort of service that makes people
    log in with MitID. Iterating its cookies gives names, not cookies, so the
    store asks for the jar underneath.
    """
    wrapped = _WrappedSession(_session_with(JSESSIONID="abc", other="def"))
    store.save(wrapped, user_id="SomeUser")

    restored = store.restore()
    assert restored is not None
    session, saved = restored
    assert dict(session.cookies) == {"JSESSIONID": "abc", "other": "def"}
    assert saved["user_id"] == "SomeUser"
    # The domain and path survive too - they are what a name and a value are
    # not enough to reconstruct.
    written = json.loads(store.path.read_text())["cookies"]
    assert {c["domain"] for c in written} == {"example.dk"}
    assert {c["path"] for c in written} == {"/"}


def test_nothing_to_restore(store):
    assert store.restore() is None
    assert store.forget() is False


def test_a_corrupted_file_is_not_a_crash(store):
    store.save(_session_with(JSESSIONID="abc"))
    store.path.write_text("{ this is not json", encoding="utf-8")
    # Better to log in again than to raise out of a cache read.
    assert store.restore() is None


def test_forgetting(store):
    store.save(_session_with(JSESSIONID="abc"))
    assert store.forget() is True
    assert not store.path.exists()
    assert store.forget() is False


def test_idle_measures_from_the_last_save(store):
    earlier = (datetime.now() - timedelta(minutes=42)).isoformat(timespec="seconds")
    idle = store.idle_for(earlier)
    assert idle is not None
    assert timedelta(minutes=41) < idle < timedelta(minutes=43)

    assert store.idle_for(None) is None
    assert store.idle_for("not a timestamp") is None


def test_the_session_is_rebuilt_by_the_factory_it_was_given(tmp_path, monkeypatch):
    """Brokers are fussy about headers, and only the caller knows which."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def picky_session() -> requests.Session:
        session = requests.Session()
        session.headers["User-Agent"] = "something a broker will accept"
        return session

    store = CookieStore("testapp", session_factory=picky_session)
    store.save(_session_with(JSESSIONID="abc"))
    restored = store.restore()
    assert restored is not None
    session, _ = restored
    assert session.headers["User-Agent"] == "something a broker will accept"


def test_a_failed_login_writes_a_private_report(store):
    path = store.write_report([{"step": "landed", "url": "https://example.dk"}])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # Next to the session it belongs to, and named after it.
    assert path.parent == store.path.parent
    assert "service-session" in path.name
    assert json.loads(path.read_text())["trace"][0]["step"] == "landed"
