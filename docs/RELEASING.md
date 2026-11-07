# Releasing ReuseFirst

ReuseFirst is installed from this repository (Claude Code's plugin marketplace
reads `.claude-plugin/marketplace.json` from the default branch), so a release
is a tag plus evidence. Nothing in CI tags, publishes or uploads; every step
below is done by the maintainer.

## Steps

1. **Bump the version in all four places**: `plugins/req-analyzer/app/reqanalyzer/__init__.py`,
   `plugins/req-analyzer/.claude-plugin/plugin.json`, the `reusefirst` entry in
   `.claude-plugin/marketplace.json`, and a new `## X.Y.Z — YYYY-MM-DD` entry at
   the top of `CHANGELOG.md`.
2. **Check:** `python3 tools/release_manifest.py --check` (the test suite runs the
   same check), then the full suite and `ruff check .`.
3. **Merge to `main`** through a pull request with green CI.
4. **Tag** the merge commit: `git tag -a vX.Y.Z -m "ReuseFirst X.Y.Z" && git push origin vX.Y.Z`.
5. **Evidence:** from a clean checkout of the tag,
   `python3 tools/release_manifest.py -o reusefirst-X.Y.Z-manifest.json`, then
   create the GitHub release and attach the manifest:
   `gh release create vX.Y.Z reusefirst-X.Y.Z-manifest.json --notes-file <notes>`.

## Verifying an install

```bash
gh release download vX.Y.Z --pattern '*-manifest.json'
python3 tools/release_manifest.py --verify reusefirst-X.Y.Z-manifest.json \
    --root ~/.claude/plugins/cache/<marketplace>/reusefirst/<version>
```

Exit code 0 means the installed plugin is exactly the released files; 1 lists
what is missing, changed or extra.

## Rolling back

Users get whatever `main` holds the next time the marketplace refreshes, so a
bad release is fixed forward: `git revert` the change on `main` through a pull
request, bump the patch version, and release again. To stay on an old version,
clone the tag (`git clone --branch vX.Y.Z https://github.com/buildsbeyondai-code/reusefirst`)
and add that folder as a local marketplace: `/plugin marketplace add ./reusefirst`.
