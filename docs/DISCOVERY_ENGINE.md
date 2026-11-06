# Discovery engine (2.0)

The pipeline is in `engine.analyze`. Every stage is deterministic and bounded in time and size.

**Stage A: requirement profile (`engine.profile`).**
- Capabilities: the key concepts, after stop words, stemming and synonym groups.
- Also extracted: languages (Python, JS/TS, Rust, Go…), platforms (Windows, macOS, Linux, Android, iOS, Web),
  integrations (Stripe, Slack, Postgres…), licence constraint and offline need.

**Stage B: providers (adapters in `sources.py`).**

| Provider | Id scheme | Limits |
|---|---|---|
| Claude plugin directory cache + installed marketplaces | `plugin-directory:<repo>/<path>`, `marketplace:<mkt>/<name>` | local files |
| GitHub search (`in:name,description,topics fork:false`) | `github:<owner>/<repo>` | ≤ 5 queries, stops on rate limit |
| npm registry search | `npm:<name>` | 1 query, 20 results |
| crates.io search | `crates:<name>` | 1 query, 20 results |

- **Deduplication** uses provider-scoped ids plus repository URL. Same name with a different repository means two
  candidates (this fixed 1.x silently dropping one).
- **Caching:** results go in a bounded LRU (256 entries, 15 min TTL). `stale` is set when shown results are older
  than 10 min. GitHub `X-RateLimit-*` headers appear in `/api/diagnostics`.
- **Scheme guard:** every API base must be https (or 127.0.0.1 for tests).
- **Not done:** PyPI has no public search API, so it is **not** a provider. Locally authorised private repositories
  are also not a provider: nothing private is sent to third parties.

**Stage C: matching (`textscore.score`).**
- `relevance = 75% IDF-weighted concept coverage + 25% TF-IDF cosine` over name, description (clipped to 350 chars)
  and topics.
- 2.0 down-weights generic action verbs (generate, track, manage, review…) to 0.35, because nouns carry the
  product meaning. This is measured in docs/BENCHMARKS.md.
- Language compatibility is checked against the profile (`pass` / `fail` / `unknown`).
- Without the optional semantic review, results carry `confidence_mode: "lexical-only (reduced confidence…)"`.
- Ties break deterministically: score, then stars, then id.

**Stage D: evidence inspection.**
- For the top 5 GitHub candidates, the README (first 20 KB, untrusted text) is fetched with 4 workers and an 8 s
  deadline.
- The concepts it confirms are listed per candidate (`evidence.confirmed_in_readme`).

**Stage E: evaluation (per candidate).**
- `relevance` (= `closeness`, kept for compatibility) and `coverage`.
- `evidence.confidence` (0–90, heuristic, uncalibrated):
  - 25 base;
  - up to +15 for a substantive description;
  - +10 for topics;
  - +25 when a README was inspected;
  - up to +15 for the share of concepts the README confirms.
- `licence` (class and reuse right), `compatibility`, `maintenance` (active / stale / unmaintained / archived) and
  `security_risk` (a maintenance-based signal only; "unknown" when active, because no vulnerability data exists at
  this stage).
- `recommendation`: reuse / extend / borrow / borrow ideas / build new / **insufficient evidence**.
- `auto_reuse_eligible` with reasons (docs/REUSE_POLICY.md).

**Stage C+: optional semantic review (`semantic.py`, 2.0.2).**
- When "Deep check with Claude" is ticked (`semantic: true`, CLI `--semantic`), Claude judges the functional fit
  (0–100), coverage, gaps and kind of the top 8 candidates. The input is their descriptions and README excerpts.
- **Safety:**
  - the call has no tools, no MCP servers (`--strict-mcp-config`), and Claude-API-only egress in the sandbox;
  - candidate text is fenced as `<untrusted>`;
  - the output is schema-validated, unknown ids are ignored, and scores are clamped.
- **Effects:**
  - recommendations use the semantic fit;
  - pre-selection requires both the lexical coverage and the fit to pass;
  - evidence confidence rises (+20, capped at 95);
  - the decision engine uses the fit and the named gaps.
- It is off by default because it spends the user's Claude usage (about $0.05–0.10 per analysis).

**Decision (`decision.py`).**
- Compares reusing the top 3 candidates (coverage ≥ 30%) with building new, in **relative effort units** (1 unit ≈
  build and test one capability).
- Capabilities are estimated as the first 8 key concepts plus a third of the rest, capped at 25. 2.0.0 counted every
  concept and inflated long requirements: 59 concepts became 61–122 units.
- Each estimate is a low–high range with listed assumptions: adaptation, missing capabilities, integration,
  licence overhead, maintenance exposure and evidence uncertainty.
- Includes a sensitivity check (what happens if missing capabilities cost twice as much).
- No-licence candidates are never "copyable". Overlapping ranges are flagged.
- `GET /api/analyses/<id>/report.md` exports the decision.
- Measured build outcomes (`/api/outcomes`, numbers only) are shown next to forecasts. They are not yet used to
  re-fit weights, because there are too few samples.

**Honest labelling.**
- Percentages are labelled *relevance*, not probability.
- No score is calibrated: there is no labelled outcome data yet.
- The benchmark labels were made by the assistant, not by independent humans.
