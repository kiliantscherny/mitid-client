# Changelog

The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/kiliantscherny/mitid-client/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kiliantscherny/mitid-client/releases/tag/v0.1.0
