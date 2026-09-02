"""Keep a logged-in session between runs, so the phone is only needed rarely.

A MitID login costs the user a tap on their phone, which means it must not
happen once per request. What a login actually produces is a set of cookies for
the service that asked for it, and those stay good until the service decides
the session has idled out - so the cookies are what gets kept.

Nothing here knows which service the cookies belong to. Name the store after
your application and, if it logs in to more than one place, after the service:

    store = CookieStore("yaybo", "tinglysning-session.json",
                        session_factory=nemlogin.new_session)

The file lands in the XDG config directory, 0600, because a live login to a
government register in someone's name is not an ordinary cache file.

Any session will do, not only `requests`: a caller whose service fingerprints
the TLS handshake will be holding a curl_cffi session instead, and both are
read and rebuilt the same way here.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path

import requests

REPORT_SUFFIX = "last-login-report.json"


def _jar(session):
    """The cookiejar to read cookies out of, whichever session this is.

    requests keeps its cookies in a jar you can iterate for cookie objects.
    curl_cffi, which callers reach for when a service fingerprints the TLS
    handshake, wraps one in a `Cookies` object that iterates *names* instead -
    so asking it for `.jar` is the difference between four fields per cookie
    and a crash on the first `.name`.
    """
    return getattr(session.cookies, "jar", session.cookies)


class CookieStore:
    """Where one application's session cookies live between runs."""

    def __init__(
        self,
        app: str,
        name: str = "session.json",
        *,
        session_factory=requests.Session,
    ) -> None:
        self.app = app
        self.name = name
        # How a restored session is rebuilt. A broker usually wants particular
        # headers on it - NemLog-in refuses a session that does not look like a
        # browser - and only the caller knows which broker it went through.
        self.session_factory = session_factory

    @property
    def path(self) -> Path:
        """Where the cached cookies live, following the XDG config convention."""
        root = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        return Path(root).expanduser() / self.app / self.name

    def save(self, session, **extra) -> Path:
        """Write the session's cookies out, readable by nobody else.

        Anything passed as `extra` is written alongside them and handed back by
        `restore` - the user ID, which service it was, whatever the caller needs
        to recognise the session later. The mode is re-applied on every write in
        case an older run left the file looser.
        """
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            # Every run rewrites this, so it records last use rather than the
            # login - which is what an idle limit actually measures.
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            **extra,
            "cookies": [
                {
                    "name": cookie.name,
                    "value": cookie.value or "",
                    "domain": cookie.domain,
                    "path": cookie.path,
                }
                for cookie in _jar(session)
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return path

    def restore(self) -> tuple[requests.Session, dict] | None:
        """Rebuild a session from the cache, with whatever was saved beside it.

        Returns None when there is nothing to restore. Says nothing about
        whether the server still honours the cookies - only the server knows
        that, and only when asked.
        """
        path = self.path
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        session = self.session_factory()
        for cookie in payload.get("cookies") or []:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain") or "",
                path=cookie.get("path") or "/",
            )
        return session, payload

    def forget(self) -> bool:
        """Delete the cached cookies. True if there was anything to delete."""
        path = self.path
        if not path.exists():
            return False
        path.unlink()
        return True

    def idle_for(self, saved_at: str | None) -> timedelta | None:
        """How long since the session was last used, as far as this machine knows."""
        if not saved_at:
            return None
        try:
            return datetime.now() - datetime.fromisoformat(saved_at)
        except ValueError:
            return None

    def write_report(self, trace: list, final=None) -> Path:
        """Write a failed login's hop-by-hop trace next to the session file.

        A login that goes wrong is only diagnosable from the pages it passed
        through, and those pages can carry a name and a CPR number - so this
        lands 0600 in the same private directory as the session itself.
        """
        path = self.path.with_name(f"{self.name.rsplit('.', 1)[0]}-{REPORT_SUFFIX}")
        path.parent.mkdir(parents=True, exist_ok=True)
        report: dict = {"trace": trace}
        if final is not None:
            report["final_url"] = final.url
            report["final_status"] = final.status_code
            report["final_html"] = final.text
        path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return path
