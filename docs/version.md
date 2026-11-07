# Package version

Git tags are the only stored copy of the Keel version. A tag `vMAJOR.MINOR.PATCH` holds the three numbers. The build is the short commit hash of that commit. The visible version is `MAJOR.MINOR.PATCH+<short hash>`.

`setuptools-scm` reads git and fills the installed package metadata. Runtime and UI code read that metadata with `keel.version.package_version()`. Do not write the version into `pyproject.toml`, Python, HTML, tests, or docs as a literal.

A pull request merged to the default branch publishes the next tag. The Version tag workflow pushes that tag as the Keel version control GitHub App (`KEEL_VERSION_APP_ID` and `KEEL_VERSION_APP_PRIVATE_KEY`), which is the actor allowed through the tag ruleset. The Version labels check rejects that pull request when more than one of `bump:major`, `bump:minor`, and `bump:patch` is set. No bump label means a minor bump. Pull requests into other branches are not checked and do not publish a tag. A direct push does not publish a tag.

When no version tag exists yet, that merge publishes the release named in [`.github/initial-version`](../.github/initial-version) and does not bump. Fetch tags before installing (`git fetch --tags`). After a new tag is on the clone, reinstall the editable package (`pip install -e ".[dev]"`) so metadata matches.

See [Version from git tags](adr/version-from-git-tags.md).

The web footer still shows `Keel` plus that version. See [Persistent version footer](adr/persistent-version-footer.md).
