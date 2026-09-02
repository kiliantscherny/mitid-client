"""Log in to a Danish public-sector site through NemLog-in, using MitID.

NemLog-in is the government's identity broker: tinglysning.dk, borger.dk,
skat.dk and the rest all delegate to it over SAML, so the flow below is not
tinglysning-specific. Point `log_in` at any NemLog-in-protected URL and it will
come back with the session cookie that URL was guarding.

The dance, once you strip the redirects away:

    1. GET the protected URL. It 302s to nemlog-in.mitid.dk/login/mitid.
    2. POST login/mitid/initialize. NemLog-in answers with the `aux` blob
       that MitID's core client needs.
    3. Run the MitID authentication (see mitid/) to get an authorisation code.
    4. POST that code back to login/mitid. NemLog-in answers with a signed
       SAML assertion in an auto-submitting form.
    5. POST the form. The service checks the assertion and sets its session.

Step 2 is the part the published reference scripts get wrong: they scrape an
`"Aux":"..."` string straight out of the login page's HTML, which NemLog-in
stopped shipping. It now sits behind that XHR instead, gated by a "Fortsæt til
login" button.
"""

from __future__ import annotations

import base64
import json
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import mitid

NEMLOGIN = "https://nemlog-in.mitid.dk"
LOGIN_PAGE = f"{NEMLOGIN}/login/mitid"
INITIALIZE = f"{NEMLOGIN}/login/mitid/initialize"

# NemLog-in is fussy about looking like a browser, and MitID's own backend
# refuses sessions that do not carry a plausible one.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Sent when following the flow's *pages*, never on the JSON calls MitID's
# backend serves - those two want to be told apart, and a session-wide Accept
# header could not.
PAGE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
}


class NemLogInError(Exception):
    """Raised when the NemLog-in flow cannot be completed."""


def new_session() -> requests.Session:
    """A requests session with the headers NemLog-in and MitID expect."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    )
    return session


def log_in(
    session: requests.Session,
    start_url: str,
    user_id: str,
    *,
    method: str = mitid.APP,
    password: str | None = None,
    choose_identity=None,
    ask_token_code=None,
    on_status=None,
    on_qr=None,
    on_otp=None,
    trace=None,
) -> requests.Response:
    """Authenticate `session` against `start_url` and return the final response.

    `user_id` is the MitID user ID (the name you type on mitid.dk, not a CPR
    number). Everything else is passed through to mitid.authenticate.

    Pass a list as `trace` to have every hop recorded into it. Logging in costs
    the user a tap on their phone, so when something goes wrong the run has to
    come back with enough detail to fix it without asking for another one.
    """
    say = on_status or (lambda message: None)

    say("Contacting NemLog-in...")
    landing = session.get(
        start_url, headers={**PAGE_HEADERS, "Sec-Fetch-Site": "none"}, timeout=60
    )
    landing.raise_for_status()
    _record(trace, "landed on NemLog-in", landing, session)
    if not landing.url.startswith(LOGIN_PAGE):
        raise NemLogInError(
            f"expected to land on {LOGIN_PAGE}, ended up at {landing.url} - "
            "either the session is already logged in or the flow has changed"
        )

    # Post back everything the page's own form holds, not just the fields we
    # care about: the browser submits the whole form, and a server that reads
    # the ones we left out would see a request no browser would ever send.
    form_fields = _form_fields(BeautifulSoup(landing.text, "html.parser").find("form"))
    verification_token = form_fields.get("__RequestVerificationToken", "")
    if not verification_token:
        raise NemLogInError(
            "no __RequestVerificationToken on the NemLog-in page - "
            "the login page has changed"
        )
    aux = _initialize(session, verification_token, referer=landing.url)

    code = mitid.authenticate(
        session,
        aux,
        user_id,
        method=method,
        password=password,
        ask_token_code=ask_token_code,
        on_status=on_status,
        on_qr=on_qr,
        on_otp=on_otp,
    )

    say("Exchanging the MitID approval for a session...")
    form_fields.update(
        {
            # The page's JavaScript sets these two: the confirmation flag the
            # moment initialize() succeeds, and the code when MitID hands it
            # over.
            "MitIDUseConfirmed": "True",
            "MitIDAuthCode": code,
            # And these two prove the submission belongs to the flow NemLog-in
            # started. It keeps the pair in cookies, the core client mirrors
            # them into sessionStorage, and the form posts them back so the two
            # can be compared. Get them wrong - or leave them empty, which is
            # what a script naturally does - and NemLog-in reads the mismatch
            # as a second browser tab: "Du er allerede logget ind".
            **_flow_state(session),
        }
    )
    response = session.post(
        LOGIN_PAGE,
        data=form_fields,
        headers={
            **PAGE_HEADERS,
            "Referer": landing.url,
            "Origin": NEMLOGIN,
            "Sec-Fetch-Site": "same-origin",
        },
        timeout=60,
    )
    response.raise_for_status()
    _record(trace, "posted the MitID authorisation code", response, session)

    return _hand_back(session, response, choose_identity, trace, say)


def _flow_state(session: requests.Session) -> dict[str, str]:
    """The flow identifiers NemLog-in expects to hear back from sessionStorage."""
    held = {"SessionUuid": "", "Challenge": ""}
    for cookie in session.cookies:
        if cookie.name in held and cookie.domain.lstrip(".").endswith(
            urlparse(NEMLOGIN).netloc
        ):
            held[cookie.name] = cookie.value or ""

    missing = [name for name, value in held.items() if not value]
    if missing:
        raise NemLogInError(
            f"NemLog-in never set its flow cookies ({', '.join(missing)}) - "
            "the login page has changed"
        )
    return {
        "SessionStorageActiveSessionUuid": held["SessionUuid"],
        "SessionStorageActiveChallenge": held["Challenge"],
    }


def _initialize(session: requests.Session, token: str, *, referer: str) -> dict:
    """Ask NemLog-in to start a MitID session and return the decoded aux blob."""
    response = session.post(
        INITIALIZE,
        data={
            "__RequestVerificationToken": token,
            # Only set when a previous MitID attempt in this browser tab was
            # interrupted. We always start fresh, so both are empty.
            "SessionStorageActiveSessionUuid": "",
            "SessionStorageActiveChallenge": "",
        },
        headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"},
        timeout=60,
    )
    response.raise_for_status()

    # The body is a JSON string that itself contains JSON, so it needs decoding
    # twice - but only when the outer layer really is a string.
    payload = response.json()
    if isinstance(payload, str):
        payload = json.loads(payload)
    if "Aux" not in payload:
        raise NemLogInError(f"no Aux in the initialize response: {payload}")

    return json.loads(base64.b64decode(payload["Aux"]))


def _hand_back(
    session: requests.Session,
    response: requests.Response,
    choose,
    trace,
    say,
    *,
    max_hops: int = 8,
) -> requests.Response:
    """Carry the assertion from NemLog-in back to the service that asked for it.

    Between the MitID approval and the service's own session there can be an
    identity chooser and one or more auto-submitting SAML forms - pages whose
    entire content is a hidden form and a line of JavaScript that submits it.
    requests has no JavaScript, so we do the submitting.

    The loop ends either at the service, or at a NemLog-in page we cannot
    account for - and says which page that was, rather than quietly handing
    back a response that was never a session.
    """
    for _ in range(max_hops):
        soup = BeautifulSoup(response.text, "html.parser")

        # Identity chooser. Recognised by what is on the page rather than by
        # its URL, which has moved before.
        if soup.select("div.list-link-box a[data-loginoptions]"):
            say("Choosing which identity to use...")
            response = _choose_identity(session, response, choose, soup)
            _record(trace, "chose an identity", response, session)
            continue

        form = soup.find("form")
        fields = _form_fields(form)
        if form is not None and fields.keys() & {"SAMLResponse", "SAMLRequest"}:
            action = urljoin(response.url, str(form.get("action", "")) or response.url)
            response = session.post(
                action,
                data=fields,
                headers={
                    **PAGE_HEADERS,
                    "Referer": response.url,
                    "Origin": f"{urlparse(response.url).scheme}://{urlparse(response.url).netloc}",
                    "Sec-Fetch-Site": "cross-site",
                },
                timeout=60,
            )
            response.raise_for_status()
            _record(
                trace,
                f"submitted a SAML form to {urlparse(action).netloc}",
                response,
                session,
            )
            continue

        if urlparse(response.url).netloc.endswith(urlparse(NEMLOGIN).netloc):
            raise NemLogInError(
                f"stopped on a NemLog-in page with nothing to submit: "
                f"{response.url}\n{_summarise(soup)}"
            )
        return response

    raise NemLogInError(
        f"still being handed between endpoints after {max_hops} hops "
        f"(currently at {urlparse(response.url).netloc})"
    )


def _choose_identity(
    session: requests.Session, response: requests.Response, choose, soup
) -> requests.Response:
    """Pick an identity when MitID resolves to more than one.

    People with a company signature see this page: the same MitID unlocks a
    private identity and one per company they can sign for.
    """
    options = []
    for box in soup.select("div.list-link-box"):
        label = box.select_one("div.list-link-text")
        link = box.find("a")
        if link is not None and link.get("data-loginoptions"):
            options.append(
                (
                    label.get_text(strip=True) if label else "?",
                    str(link["data-loginoptions"]),
                )
            )

    if len(options) == 1:
        chosen = 0
    elif choose is None:
        raise NemLogInError(
            "MitID resolved to several identities and there is no way to pick one: "
            + ", ".join(label for label, _ in options)
        )
    else:
        chosen = choose([label for label, _ in options])

    form = soup.find("form")
    if form is None:
        raise NemLogInError("the identity page has no form to submit")
    fields = _form_fields(form)
    fields["ChosenOptionJson"] = options[chosen][1]
    # This page belongs to the same flow as the login page, and is checked the
    # same way. Leaving these out is what turns a chosen identity into
    # "Du er allerede logget ind".
    fields.update(_flow_state(session))

    posted = session.post(
        urljoin(response.url, str(form.get("action", "")) or response.url),
        data=fields,
        timeout=60,
    )
    posted.raise_for_status()
    return posted


def _form_fields(form) -> dict[str, str]:
    """Every named input a browser would submit, hidden ones included.

    Unticked checkboxes and unselected radios are left out, because a browser
    leaves them out - and one of these pages carries an `acceptTerms` box that
    we have no business ticking on the user's behalf.
    """
    if form is None:
        return {}
    fields = {}
    for field in form.find_all("input"):
        name = field.get("name")
        if not name:
            continue
        kind = str(field.get("type", "")).lower()
        if kind in ("checkbox", "radio") and not field.has_attr("checked"):
            continue
        fields[str(name)] = str(field.get("value", ""))
    return fields


def _summarise(soup) -> str:
    """What a page says, for an error message that has to explain itself."""
    title = soup.find("title")
    text = " ".join(soup.get_text(" ").split())
    forms = [
        f"{str(form.get('method', 'GET')).upper()} {form.get('action', '')} "
        f"[{', '.join(sorted(_form_fields(form)))}]"
        for form in soup.find_all("form")
    ]
    lines = [f"  title: {title.get_text(strip=True) if title else '(none)'}"]
    lines += [f"  form: {form}" for form in forms]
    lines.append(f"  text: {text[:400]}")
    return "\n".join(lines)


def _record(trace, step: str, response: requests.Response, session=None) -> None:
    """Note one hop, in enough detail to work out afterwards what happened."""
    if trace is None:
        return
    session = session if session is not None else requests.Session()
    soup = BeautifulSoup(response.text, "html.parser")
    trace.append(
        {
            "step": step,
            "status": response.status_code,
            "url": response.url,
            "redirects": [hop.url for hop in response.history],
            "new_cookies": sorted({cookie.name for cookie in response.cookies}),
            "session_cookies": sorted({cookie.name for cookie in session.cookies}),
            "forms": [
                {
                    "action": form.get("action", ""),
                    "method": str(form.get("method", "GET")).upper(),
                    "fields": sorted(_form_fields(form)),
                }
                for form in soup.find_all("form")
            ],
            "summary": _summarise(soup),
            # The page itself, because the thing that finally explains a
            # failure is usually the inline script we could not have guessed at.
            "html": response.text,
        }
    )
