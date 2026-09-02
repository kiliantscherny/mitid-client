# mitid-client

Log in to Danish services with MitID, from Python. No browser, no Selenium.

---

> [!CAUTION]
> **This is a hobby project. It is not built for production use, and nothing
> about it is supported.**
>
> It is not affiliated with, endorsed by, or connected to MitID,
> NemLog-in, Digitaliseringsstyrelsen, Nets, Signicat, or any service that
> authenticates through them. Those names appear here only to say what this
> talks to.
>
> Provided as-is, with no warranty of any kind. **Use it at your own risk.** The
> author accepts no liability for any loss, damage, lockout, or misuse arising
> from it.

Every MitID-protected site works the same way. An identity broker hands the
browser an `aux` blob, the browser feeds that to MitID's JavaScript core client,
and the core client hands back an authorisation code the broker exchanges for a
session. This package is a Python stand-in for that core client, plus the
brokers and the two ways of showing a login to the person doing it.

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
| `mitid.brokers.nemlogin` | NemLog-in, which fronts the whole Danish public sector            |
| `mitid.store`            | keeps a login's cookies between runs, 0600, in `$XDG_CONFIG_HOME` |
| `mitid.ui.console`       | status lines, a scannable QR and a code box, on stderr            |
| `mitid.ui.tui`           | the same login as a Textual screen (`[textual]` extra)            |

The protocol reports everything through callbacks — `on_status`, `on_qr`,
`on_otp`, `ask_token_code`, `choose_identity` — and draws nothing itself. That
is the whole reason the same login can be a few lines on stderr in one program
and a screen in another.

## Logging in

Two methods. `APP` sends a request to the MitID app and shows either a QR to
scan or a six-digit code to type, whichever the app asks for; `TOKEN` takes six
digits from a code token followed by the account password.

```python
from mitid.ui.console import LoginConsole

screen = LoginConsole()
final = nemlogin.log_in(
    session, START_URL, user_id,
    on_status=screen.status,     # progress, and which service is asking
    on_qr=screen.qr,             # a QR matrix, redrawn in place each second
    on_otp=screen.otp,           # a code to type into the app
    ask_token_code=screen.ask,   # only with method=mitid.TOKEN
    choose_identity=screen.choose,  # when one MitID unlocks several identities
)
```

In a Textual application, the same login is a screen:

```python
from functools import partial
from mitid.ui.tui import MitIDLoginScreen

result = await self.push_screen_wait(
    MitIDLoginScreen(partial(nemlogin.log_in, session, START_URL))
)
```

`MitIDLoginScreen` calls what you give it with the five callbacks above and
dismisses with whatever it returns, or `None` if the user gave up.

## Keeping the session

A login costs a tap on a phone, so it must not happen once per request. What it
produces is a set of cookies, and `CookieStore` keeps those between runs:

```python
from mitid.store import CookieStore

store = CookieStore("yourapp", "service-session.json",
                    session_factory=nemlogin.new_session)
store.save(session, user_id=user_id)

restored = store.restore()          # (session, saved) or None
if restored:
    session, saved = restored
    idle = store.idle_for(saved["saved_at"])
```

Whether the service still honours those cookies is between you and the service —
ask it. Most of them end a session that has sat idle for half an hour.

## Installing

```sh
uv add mitid-client              # or: pip install mitid-client
uv add "mitid-client[textual]"   # if you want the Textual screen
```

Not on PyPI yet. Until it is, depend on it by path or by git:

```toml
[tool.uv.sources]
mitid-client = { path = "../mitid-client", editable = true }
# or
mitid-client = { git = "https://github.com/kiliantscherny/mitid-client.git" }
```

## Known to work against

Two brokers, in two applications, which is the whole reason this is a library
rather than a file copied between them:

| service        | broker    |
| -------------- | --------- |
| tinglysning.dk | NemLog-in |
| nordnet.dk     | Signicat  |

`mitid.brokers.nemlogin` covers the first shape and is reusable as it stands:
point it at any NemLog-in-protected URL. The second shape does its own dance to
get an `aux` blob and then calls `mitid.authenticate` with it, which is the part
every service has in common.

## Tests

```sh
uv run pytest
```

Everything that can be tested without a phone is: the cookie store's round trip
and file mode, both QR renderers' shape and polarity, and the unwrapping of
MitID's error responses. The protocol itself is not - it can only be exercised
against the real thing.

## Credits and licence

`mitid/core.py` and `mitid/srp.py` are adapted from
[Hundter/MitID-BrowserClient](https://github.com/Hundter/MitID-BrowserClient),
MIT-licensed, © 2024 Hundter.

MIT. See `LICENSE`.

## What you are taking on

> [!WARNING]
> This logs in **as you**, with a national electronic identity, over a protocol
> that is not a published API — it is reverse-engineered from what a browser
> does. The consequences of that are real, and they are yours:
>
> - MitID can rate-limit an account, and **temporarily block one**, after
>   repeated failed authentications. A login flow that is wrong in a loop is a
>   good way to find that out.
> - The protocol can change without notice, and when it does this stops
>   working — possibly halfway through a login.
> - Every service you point this at has terms of service, and they apply to
>   you. So does the law.
> - A saved session is a **live credential**. `CookieStore` writes it `0600` in
>   your config directory; where it goes after that is your problem.

> [!IMPORTANT]
> None of this has been security-audited, and it is not a security product. It
> handles credentials, tokens and cookies on a best-effort basis. Do not put it
> anywhere that anybody else's identity depends on it.

Use it for your own accounts and your own data.
