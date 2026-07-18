# How I measure accuracy in document-extraction AI pipelines

*Draft for LinkedIn/blog — Artifact 2 of the roadmap. Numbers current as of
the 2026-07-18 held-out re-run (post per-page extraction fix).*

---

Everyone's demo extracts documents. Almost nobody can tell you their
transaction-level F1, per field, on data the pipeline has never seen — or what
it costs per document to get it.

I just shipped [DocVal](https://github.com/Sero01/docval), a bank-statement
extraction and validation pipeline with a
[live demo](https://docval-yy4s.onrender.com). The extraction part — hybrid
native-PDF parsing with a vision-LLM fallback for scans — took a day or two.
The part that took real engineering judgment was the measurement: knowing,
continuously and honestly, when the pipeline is wrong. That's what this
writeup covers.

## Three layers, in order of trust

1. **Schema enforcement** (cheapest): every extraction, native or vision, must
   land in the same Pydantic model — typed dates, decimal amounts, at most one
   of debit/credit per row. The vision model returns a *wire* schema of plain
   strings; normalization to canonical types is deterministic code, because
   models copy what's printed no matter how nicely you ask.
2. **Deterministic validation** (free, runs on every document): does
   opening balance + every transaction equal the closing balance? Does the
   running-balance chain hold row by row? Are dates inside the statement
   period, in order? These are pure functions over the schema — no model in
   the loop, no false authority. A statement that passes balance continuity
   has a *structurally* correct extraction, which no LLM judge can promise.
3. **The eval harness** (costs money, run deliberately): ground-truth
   comparison on a held-out set, producing the numbers below.

## Eval design decisions that actually mattered

**Transaction matching must be earned, not fuzzy.** My row matcher aligns a
predicted transaction to gold only on exact date + exact signed amount, with
description similarity as a tie-breaker (SequenceMatcher ≥ 0.6). Fuzzy-matching
amounts would inflate scores on precisely the failure mode that matters in
finance — a wrong amount *is* the error.

**Split the numbers by data source, or you're lying to yourself.** My headline
held-out F1 is **0.63**. Sounds mediocre. The split tells the real story:
**0.92 on synthetic statements, 0.42 on real scanned Indian bank statements**
(dense 6-page, ~160-transaction documents) — and that 0.42 was **0.12** before
the paged-extraction fix the harness pointed at. One aggregate number would
have hidden both that the pipeline works and where it breaks.

**Beware circular evals.** My synthetic generator and my native parser
understand the same layouts — evaluating the native path on generated
documents partly measures agreement between two things I wrote. Real
third-party documents are the only numbers I fully trust, which is why they're
reported separately, and why the weakest number goes in the README.

**Twin leakage.** The public dataset I used ships each statement twice —
a digital PDF and a pixel-rendered scan with byte-identical ground truth.
Random splitting would put one twin in dev and its sibling in held-out:
invisible leakage, inflated scores. Split curation put twins in the same
split. Check for this in any dataset with derived variants.

**Track cost and latency as first-class metrics.** Every eval row records
tokens and dollars ($0.008/doc mean on the held-out run, all retries billed).
An accuracy gain that 10×es cost is a different decision than a free one.

## The regression gate

The full harness costs money, so CI runs a free subset on every push: an
offline manifest through the native path, compared against a committed
baseline with a 1-point tolerance:

```
uv run python -m eval.run_eval --manifest tests/fixtures/ci_manifest.jsonl --no-vision
uv run python -m eval.compare results.json eval/baseline_ci.json
```

Nobody remembers to run evals manually. A red ✗ on a PR is the only eval
discipline that survives contact with a deadline.

## What the harness caught (that vibes never would)

- **Output-cap truncation as the dominant failure.** 10 of 13 held-out errors
  were the model blowing through a 32k output-token cap on dense documents —
  not "bad extraction," but a structural failure mode with a structural fix
  (page-by-page extraction with merged results, sanity-checked by the
  running-balance validator). The fix took real-scan F1 from **0.12 to 0.42**
  and the error rate from **13% to 1%**, at ~1.6× the per-doc cost.
- **Model nondeterminism at temperature 0.** The same document flipped
  validation pass→fail between identical reruns. If your eval runs once,
  some of your "improvements" are noise.
- **Provider flakiness masquerading as model failure.** Mid-stream aborted
  responses ("error injected into SSE stream") initially looked like model
  errors. Separating transient infrastructure failures (retry with backoff)
  from persistent model failures (fix the approach) changed the error rate
  from 36% to 13% without touching the model.
- **A third-party benchmark with a broken scorer.** I submitted to a public
  bank-statement benchmark; every document was rejected by a server-side
  ground-truth bug — which I could only prove by submitting the benchmark's
  *own example payload* as a control. Trust third-party numbers, but verify
  the third party. ([Issue filed.](https://github.com/bankstatemently/bank-statement-parsing-benchmark/issues/1))
- **Currency symbols vs ISO codes.** Benchmark documents printed `$` where
  the schema wanted `USD`. Found in minutes because validation failures
  pointed at the exact field. Normalization is now deterministic code with a
  test — the model never gets asked to do it.

## The numbers (held-out, 100 documents, never used for tuning)

| Metric | Value |
|---|---|
| Transaction F1 | 0.63 — synthetic 0.92 / real scans 0.42 |
| Header field accuracy | 0.87 |
| Validation pass rate | 0.25 |
| Error rate | 0.01 |
| Mean cost per document | $0.008 |

Publishing the 0.42 feels bad. It's also the entire point: that number is
where the work is, and a pipeline whose owner knows its worst number is more
deployable than one with a single proud aggregate.

## Takeaways

1. Deterministic validation beats LLM-judged "quality" — arithmetic doesn't
   hallucinate.
2. Report accuracy split by data source; aggregates hide exactly what you
   need to know.
3. Put the regression gate in CI where it can't be skipped.
4. Separate transient failures from persistent ones before "fixing" anything.
5. Record cost per document next to accuracy — they trade off, visibly.
6. Your worst honest number is your roadmap.

---

*DocVal is open source: [github.com/Sero01/docval](https://github.com/Sero01/docval).
Live demo: [docval-yy4s.onrender.com](https://docval-yy4s.onrender.com). I build
document-extraction and reconciliation systems for financial operations.*
