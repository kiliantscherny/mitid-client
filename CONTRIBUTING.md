# Contributing

> [!NOTE]
> This is a hobby project. Issues and pull requests are welcome, but there is
> no roadmap and no support commitment.

## Setup

You need [uv](https://docs.astral.sh/uv/). Python comes with it.

```sh
git clone https://github.com/kiliantscherny/mitid-client.git
cd mitid-client
uv sync --all-extras
```

Optionally, install the pre-commit hooks with
[prek](https://github.com/j178/prek):

```sh
prek install
```

That runs ruff, ty and `uv lock --check` before each commit, which is most of
what CI would have told you a few minutes later.

## Running the checks

```sh
uv run tox           # tests on 3.10-3.14, plus lint, format and types
uv run pytest        # just the tests, on the local interpreter
uvx ruff@0.16.5 check   # lint
uvx ruff@0.16.5 format  # format
uvx ty@0.0.37 check     # types
```

`.python-version` pins local development to **3.10**, the oldest version the
package supports. Working there means syntax or stdlib calls that need
something newer fail immediately, rather than passing locally and breaking for
someone on the version you claim to support.

## Layout

```
src/mitid/
├── __init__.py        authenticate(): an aux blob in, an authorisation code out
├── core.py            the core client: SRP, the app channel, QR frames, polling
├── srp.py             SRP-6a and the AES-GCM bits the authenticators need
├── brokers/
│   └── nemlogin.py    NemLog-in, which fronts the Danish public sector
├── store.py           keeping a login's cookies between runs
└── ui/
    ├── console.py     status lines, a QR and a code box, on stderr
    └── tui.py         the same login as a Textual screen

tests/                 everything that can be checked without a phone
```

> [!IMPORTANT]
> `core.py` and `srp.py` come from
> [Hundter/MitID-BrowserClient](https://github.com/Hundter/MitID-BrowserClient)
> and are kept deliberately close to it, so that upstream fixes can be dropped
> straight in when MitID changes the protocol.
>
> They are formatted, linted and type checked like everything else, and every
> change made to them is listed at the top of each file. There is one `noqa`
> between them, on the SRP group modulus, which is a 942-digit integer literal
> that Python offers no way to split.
>
> Because they have been reformatted, a diff against upstream is no longer
> readable directly. When MitID changes the protocol, diff upstream against
> upstream and apply the change here by hand. Behavioural changes are worth
> raising upstream too.

## Adding a broker

A broker is the part that starts an authentication session with a service and
hands over the `aux` blob. Everything after that is the same everywhere and
already handled by `mitid.authenticate`.

`brokers/nemlogin.py` is the worked example. A new one needs to get to an
`aux`, call `mitid.authenticate` with it, and exchange the returned
authorisation code for whatever the service treats as a session. Keep the
callbacks (`on_status`, `on_qr`, `on_otp`, `ask_token_code`,
`choose_identity`) flowing through, so both UIs keep working.

## Tests

The protocol cannot be tested without a real MitID and a real phone, so what is
covered is everything around it: the cookie store's round trip and file mode,
both QR renderers' shape and polarity, and the parsing of MitID's error
responses. There is no coverage target, and there shouldn't be: the largest
part of this package is untestable by nature, so a percentage would only
measure that.

If you change a broker or the protocol, say in the pull request which service
you ran it against and whether the login actually completed.

## Commits and releases

Commit messages are plain prose, written in the imperative, explaining why
rather than what. There is no conventional-commit or changelog automation here.

Releases are cut by hand and published by CI. See [RELEASING.md](RELEASING.md).

## Licence

By contributing you agree that your contributions are licensed under the MIT
Licence, as in [LICENSE](LICENSE).
