# Reuse policy (2.0)

Deterministic and code-enforced (`policy.py`, `reuse.py`). Rank alone never selects anything.

## Licence classes
| Class | SPDX examples | Reuse | Meaning |
|---|---|---|---|
| permissive | MIT, MIT-0, Apache-2.0, BSD-2/3-Clause, ISC, 0BSD, Unlicense, Zlib, BSL-1.0, CC0-1.0, PSF-2.0 | **allowed** | Code may be copied with the copyright notice and licence text kept |
| weak-copyleft | MPL-2.0, LGPL-*, EPL-*, CDDL-1.0 | review | A human must review before copying |
| strong-copyleft | GPL-*, AGPL-*, EUPL-1.2, OSL-3.0 | review | The whole app would need a compatible licence |
| restricted | CC-BY-NC*, SSPL, BUSL, Elastic-2.0, Commons-Clause | learn-only | Not for code reuse |
| none | no licence | learn-only | All rights reserved: never copied |
| unknown | NOASSERTION, unrecognised ids | review | A human must review |

After cloning, the LICENSE file's text is matched against known licence texts. If it disagrees with the registry's
SPDX id, the reuse status becomes **review**.

## Automatic pre-selection (Build tab)
A candidate is pre-ticked only if **all** of these hold:
- a structurally valid GitHub URL;
- concept coverage ≥ 50%;
- licence reuse = allowed;
- not archived or unmaintained (last push within 2 years);
- compatibility not `fail`;
- evidence confidence ≥ 50%;
- not a fork.

At most 3 repositories and 2 plugins are pre-ticked. When none qualify, nothing is ticked and the form shows why for
each option. The user can still tick anything by hand. Licence rules are applied at clone time either way.

## Clone and provenance (PREPARING stage)
ReuseFirst clones each ticked source in the sandbox, with GitHub-only egress and no credentials:

`git -c core.hooksPath=/dev/null -c protocol.file.allow=never -c protocol.ext.allow=never -c core.fsmonitor=false
clone --depth 1 --no-recurse-submodules --single-branch [--branch <ref>]`

- The commit SHA is read from the files git wrote, without executing git on the host.
- Sources whose final reuse status is not `allowed` are deleted.
- `upstream/` is added to `.gitignore`.
- `docs/REUSE_PROVENANCE.md` records, per source: URL, sub-path, pinned commit, licence class, reuse status and
  decision.
- The `provenance` verification gate fails if the document is missing, or if `upstream/` would be committed.

## Human review
`review` and `learn-only` sources are listed in REUSE_PROVENANCE.md as needing human review and are not available to
the agent. ReuseFirst gives no legal advice. Its table is a conservative engineering default.
