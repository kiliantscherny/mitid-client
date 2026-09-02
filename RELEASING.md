# Releasing

## Versioning

[Semantic versioning](https://semver.org/). While this is `0.x`, a breaking
change bumps the minor and everything else bumps the patch.

The public API is `mitid.authenticate`, `mitid.APP`, `mitid.TOKEN`,
`mitid.MitIDError`, `mitid.brokers.*`, `mitid.store.CookieStore` and
`mitid.ui.*`. What `core.py` and `srp.py` do internally is not part of it.
MitID changes its protocol from time to time, and following it is a patch here
even when the diff is large, as long as the callbacks and the return value stay
the same.

## Cutting one

```sh
uv version --bump patch          # or minor, or major
$EDITOR CHANGELOG.md             # move Unreleased into the new version
git commit -am "Release $(uv version --short)"
git tag "v$(uv version --short)"
git push && git push --tags
```

Pushing the tag is the release. `release.yml` checks the tag against
`pyproject.toml`, runs the tests, builds, publishes to PyPI and opens a GitHub
release with that version's changelog section. A tag that disagrees with the
version fails before anything is published.

## First-time setup

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/),
so there is no API token in the repository or in GitHub secrets. It needs two
things set up once.

**On PyPI**, at [publishing settings](https://pypi.org/manage/account/publishing/),
add a pending publisher:

| field | value |
| --- | --- |
| PyPI project name | `mitid-client` |
| Owner | `kiliantscherny` |
| Repository name | `mitid-client` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

**On GitHub**, under Settings → Environments, create an environment called
`pypi`. Adding yourself as a required reviewer there turns every release into a
button you have to press, which is worth it for a package that logs people in.
