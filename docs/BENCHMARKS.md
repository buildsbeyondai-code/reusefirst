# Benchmarks

All numbers below were measured on 2026-11-06 on the author's PC (WSL2 Ubuntu, 7.8 GB RAM, Python 3.14). Reproduce
them with the commands given.

## Retrieval quality (`python3 tests/benchmark/run_benchmark.py`)
**Corpus:** the real local Claude plugin directory cache (3,833 plugins after 2.0 deduplication).

**Queries:** 12 requirements in `tests/benchmark/queries.json`. They include hard cases:
- different wording for the same capability (Jira or tickets, migrations);
- a language-specific request (Python tests, where a Ruby gem is a lexical trap);
- an unrelated-vocabulary trap (water intake vs CO2 and water-usage status lines);
- a no-good-solution case (q12: no phone water tracker exists among the plugins).

**Judgements:**
- 201 pooled candidates: the union of the top 15 from each ranker.
- Graded 0/1/2. Three items that only v2 surfaced were judged afterwards (pool extension).
- Labels and the pool are committed (`qrels.json`, `snapshot.json` with the catalog's document frequencies), so the
  run is offline and deterministic.

| Ranker | P@5 | R@10 | MRR | NDCG@10 |
|---|---|---|---|---|
| v1 (1.x lexical) | 0.717 | 0.724 | 0.917 | 0.740 |
| **v2 (2.0, action-verb weighting)** | **0.750** | **0.771** | **0.958** | **0.763** |

- v2 is better on all four metrics, a modest improvement.
- Per query (NDCG@10), v2 is better on 6, equal on 4 and worse on 2: q02 ("review pull requests", 0.70 → 0.51) and q04
  (0.84 → 0.78). q02 is worse because "review" is in the down-weighted verb list.
- The verb list was fixed **before** it was evaluated, and it was not tuned afterwards, to avoid overfitting the
  author's own labels.
- A first v2 attempt (counting the name twice) was **worse** (NDCG@10 0.717) and was dropped.
- `tests/test_benchmark.py` fails CI if v2 falls below v1.

**Limitations (important).**
- The labels were produced by the assistant reading names and descriptions. They are **not independent human
  judgements**, and the same model family wrote the ranker. The evaluation is therefore partly circular.
- 12 queries is a small set, and the pooled judgements leave items unjudged outside the pool.
- Only the plugin corpus is benchmarked. GitHub, npm and crates.io ranking is NOT VERIFIED by a labelled benchmark.
- No calibration of displayed scores was possible.

## Latency (measured)
| Operation | Result |
|---|---|
| Catalog load (3,833 plugins, incl. import) | 0.17 s |
| Analysis without network (plugins only), 15 runs | median 44 ms, p95 47 ms |
| Ranking per query over the 201-item benchmark pool | ~6 ms |
| Sandbox start and exit (`true`, systemd scope + bwrap) | median 0.07 s |
| Sandbox self-test (13 probes) | 0.10 s |
| Full test suite (unit, integration, security, sandbox, fakes) | see docs/FINAL_AUDIT.md |

Analysis with GitHub is dominated by the network: up to 5 search calls, 5 README fetches and 2 registry searches.
1.x measured ~10 s unauthenticated. 2.0 adds the README and registry calls under 8 s / 25 s deadlines. This was
NOT re-measured under controlled network conditions.

## Product value: building with vs without ReuseFirst (`tools/value_benchmark.py`)
- The harness is ready. It runs 3 tasks × 2 arms (no reuse vs ReuseFirst's pre-selected reuse) × N trials, with the
  same model, prompt template, sandbox, limits and verification gates.
- It reports median and IQR of wall time and model-reported cost, verification status, tests passed and failed
  gates.
- **Live measurements: PENDING.** They need explicit approval to spend real Claude usage (worst case $54 for 3
  trials at a $3 cap).
- No saving is claimed.

## Mutation check (`python3 tools/mutate.py`)
- 16 controlled faults in high-risk controls: auth, origin, Content-Length, namespaces, environment clearing, egress
  allowlist, private-address block, URL parsing, licence eligibility, number ranges, enhancement manifest, gate
  decision, test-result parsing, state machine, licence-based clone removal and secret redaction.
- **16/16 killed.**
- Two equivalent mutants were found and documented in the script: `isfinite` is redundant with the range check, and
  `--tmpfs HOME` is redundant with bwrap's root tmpfs.
