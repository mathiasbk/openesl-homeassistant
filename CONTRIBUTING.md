# Contributing

Thanks for helping with the OpenESL integration for Home Assistant. The firmware, the AP and its API live in [OpenESL](https://github.com/mathiasbk/openESL); this repository is only the Home Assistant side.

## Branches

- `development` is where all pull requests go.
- `main` is the release branch. Nothing is pushed or merged to it except a release (see [Releases](#releases)). HACS installs from the releases, and the wiki is published from `main`.
- Branch from `development` with a short descriptive name, e.g. `send-image-crop`.

## Build and test locally

Run what CI runs before you push: `pip install -r requirements_test.txt`, then `pytest`. For the test against the OpenESL simulator, see "For developers" in the [README](README.md#for-developers). `python3 tools/check_wiki.py` checks the wiki's links and `python3 tools/changelog.py --check` the changelog.

## Pull request

- Target `development`.
- Fill in the template: what changed, how you tested it, and what breaks if it is wrong.
- Keep it to one change. Docs that describe the change go in the same pull request: the README, and the wiki pages in `wiki/` (edit them there, not on GitHub's wiki pages).
- A change users notice gets a line in [CHANGELOG.md](CHANGELOG.md) under the next version.
- Title and body in English.

## Review and merge

- Every pull request is reviewed before it is merged, and CI must be green.
- Pull requests are squash-merged into `development`, so the history has one commit per pull request.

## Releases

Releases are made from `development` by the maintainer, in two pull requests:

1. Into `development`: the new `version` in `custom_components/openesl/manifest.json` and its section in [CHANGELOG.md](CHANGELOG.md), which must say how to upgrade (CI checks it).
2. From `development` into `main`, titled "Release X.Y.Z", merged with a merge commit. When the manifest version changes on `main`, `.github/workflows/release.yml` tags `vX.Y.Z` and makes the GitHub release, so HACS offers it.
