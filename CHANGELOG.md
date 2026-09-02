# Changelog

The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

## [0.1.2] - 2026-09-02

### Fixed

- `CookieStore` could only read a `requests` session. A curl_cffi session -
  what a caller reaches for when the service fingerprints the TLS handshake,
  which describes a lot of what MitID fronts - wraps its cookiejar in an object
  that iterates cookie *names*, so saving one raised `AttributeError` on the
  first `.name`. The store now asks for the jar underneath, and reads all four
  fields off either shape.

## [0.1.1] - 2026-09-02

### Fixed

- `BrowserClient` built a `requests.Session` in its signature's default, which
  evaluates once at import. Every client created without an explicit session
  shared that one, cookies and all. The default is `None` now and each client
  builds its own. Callers that pass a session, which is all of them here, are
  unaffected.

### Changed

- The whole package is formatted, linted and type checked, including the two
  files adapted from upstream, which were previously exempt. No behaviour
  changed: the long strings in the protocol code are split with implicit
  concatenation and produce the same values, and the one that feeds an HMAC was
  checked byte for byte.

## [0.1.0] - 2026-09-02

First release. Split out of [yaybo](https://github.com/kiliantscherny/yaybo),
where it began as a vendored copy of MitID's core client and grew into
something two applications depended on.

### Added

- `mitid.authenticate`: an `aux` blob and a user ID in, an authorisation code
  out. Both login methods, `APP` and `TOKEN`.
- `mitid.brokers.nemlogin`: the NemLog-in broker, which fronts the Danish
  public sector. Point it at any NemLog-in-protected URL.
- `mitid.store.CookieStore`: keeps a login's cookies between runs, `0600`, in
  `$XDG_CONFIG_HOME`, and writes a private trace when a login fails.
- `mitid.ui.console.LoginConsole`: status lines, a scannable QR redrawn in
  place, and a code box, on stderr.
- `mitid.ui.tui.MitIDLoginScreen`: the same login as a Textual screen, behind
  the `textual` extra.

[Unreleased]: https://github.com/kiliantscherny/mitid-client/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/kiliantscherny/mitid-client/releases/tag/v0.1.2
[0.1.1]: https://github.com/kiliantscherny/mitid-client/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/kiliantscherny/mitid-client/releases/tag/v0.1.0
