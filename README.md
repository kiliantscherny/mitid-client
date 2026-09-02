# mitid-client

Log in to Danish services with MitID, from Python. No browser, no Selenium.

---

> [!CAUTION]
> **A hobby project, not a product.** Nothing here is supported or built for
> production use.
>
> Not affiliated with or endorsed by MitID, NemLog-in, Digitaliseringsstyrelsen,
> Nets, Signicat, or any service that authenticates through them.
>
> Provided as-is, with no warranty. **Use it at your own risk.** The author
> accepts no liability for any loss, damage, lockout or misuse.

Every MitID-protected site works the same way. An identity broker hands the
browser an `aux` blob, the browser feeds that to MitID's JavaScript core client,
and the core client returns an authorisation code the broker swaps for a session.
This package is a Python version of that core client, plus a broker for the
public sector and two ways to put a login on screen.

```python
import requests
from mitid.brokers import nemlogin

session = nemlogin.new_session()
final = nemlogin.log_in(session, "https://www.tinglysning.dk/...", "MyMitIDUserID")
# `session` now carries the service's own login cookies.
```

## What is in it

| module                   | what it does                                                      |
| ------------------------ | ----------------------------------------------------------------- |
| `mitid.authenticate`     | an `aux` blob and a user ID in, an authorisation code out         |
| `mitid.core`             | the core client: SRP, the app channel, the QR frames, polling     |
| `mitid.srp`              | SRP-6a and the AES-GCM bits the authenticators need               |
| `mitid.brokers.nemlogin` | NemLog-in, which fronts the Danish public sector                  |
| `mitid.store`            | keeps a login's cookies between runs, 0600, in `$XDG_CONFIG_HOME` |
| `mitid.ui.console`       | status lines, a scannable QR and a code box, on stderr            |
| `mitid.ui.tui`           | the same login as a Textual screen                                |

The protocol draws nothing itself. It reports progress through callbacks
(`on_status`, `on_qr`, `on_otp`, `ask_token_code`, `choose_identity`), which is
what lets the same login be a few lines on stderr in one program and a screen in
another.

## Logging in

Two methods. `APP` sends a request to the MitID app and shows either a QR to
scan or a six-digit code to type, whichever the app asks for. `TOKEN` takes six
digits from a code token, followed by the account password.

```python
from mitid.ui.console import LoginConsole

screen = LoginConsole()
final = nemlogin.log_in(
    session,
    START_URL,
    user_id,
    on_status=screen.status,  # progress, and which service is asking
    on_qr=screen.qr,  # a QR matrix, redrawn in place each second
    on_otp=screen.otp,  # a code to type into the app
    ask_token_code=screen.ask,  # only with method=mitid.TOKEN
    choose_identity=screen.choose,  # when one MitID unlocks several identities
)
```

[Textual](https://github.com/Textualize/textual) is a framework for building
terminal UIs. If your app uses it, the same login is a screen instead:

```python
from functools import partial
from mitid.ui.tui import MitIDLoginScreen

result = await self.push_screen_wait(
    MitIDLoginScreen(partial(nemlogin.log_in, session, START_URL))
)
```

`MitIDLoginScreen` calls what you give it with the five callbacks above and
dismisses with whatever it returns, or `None` if the user gave up. It renders the
QR, the code, the token prompt and the identity chooser, and runs the login on a
worker thread so the UI stays responsive. Textual is an optional dependency, so
install `mitid-client[textual]` if you want it.

## Keeping the session

A login costs a tap on a phone, so it must not happen once per request. What it
produces is a set of cookies, and `CookieStore` keeps those between runs:

```python
from mitid.store import CookieStore

store = CookieStore(
    "yourapp", "service-session.json", session_factory=nemlogin.new_session
)
store.save(session, user_id=user_id)

restored = store.restore()  # (session, saved) or None
if restored:
    session, saved = restored
    idle = store.idle_for(saved["saved_at"])
```

Whether the service still honours those cookies is up to the service, so ask it.
Most end a session that has sat idle for half an hour.

## Which services it works with

Any service that authenticates through MitID, in principle. What differs between
them is the broker: the part that starts the session and hands over the `aux`
blob. Once you have that blob, `mitid.authenticate` does the rest, and that half
is the same everywhere.

`mitid.brokers.nemlogin` covers NemLog-in, which fronts the Danish public sector.
Point it at any NemLog-in-protected URL and it should work as it stands. Other
brokers need a short module of their own to fetch the `aux` blob; `nemlogin.py`
is the worked example to copy from.

Tried so far against tinglysning.dk (NemLog-in) and nordnet.dk (Signicat).

## Installing

```sh
uv add mitid-client              # or: pip install mitid-client
uv add "mitid-client[textual]"   # for the Textual screen
```

## What you are taking on

> [!WARNING]
> This logs in **as you**, with a national electronic identity, over a protocol
> that is not a published API. It is reverse-engineered from what a browser does.
>
> - MitID can rate-limit an account, and temporarily block one, after repeated
>   failed logins. A broken login flow running in a loop will get you there.
> - The protocol can change without notice. When it does, this stops working,
>   possibly halfway through a login.
> - The terms of service of whatever you point this at still apply to you.
> - A saved session is a live credential. `CookieStore` writes it `0600` in your
>   config directory, and after that it is yours to look after.

> [!IMPORTANT]
> This has not been security-audited and is not a security product. It handles
> credentials, tokens and cookies on a best-effort basis. Don't build anything on
> it that other people's identities depend on.

Use it for your own accounts and your own data.

## Tests

```sh
uv run pytest
```

Covers the cookie store's round trip and file mode, both QR renderers' shape and
polarity, and the parsing of MitID's error responses. The protocol itself is not
covered. It can only be run against the real thing.

## Credits and licence

The protocol here was worked out by
[Hundter/MitID-BrowserClient](https://github.com/Hundter/MitID-BrowserClient),
MIT-licensed, © 2024 Hundter. `mitid/core.py` and `mitid/srp.py` started as
that code and have been changed since.

MIT. See `LICENSE`.
