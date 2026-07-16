# DocVal

Bank-statement extraction + validation pipeline. Extracts statements to
structured JSON (native text-layer parsing when possible, Gemini 2.5 Flash
vision via OpenRouter for scans), then **validates the arithmetic** — balance
continuity is the star check: does opening balance + every transaction really
equal the closing balance?

<!-- CI badge: uncomment after first push
![ci](https://github.com/<user>/docval/actions/workflows/ci.yml/badge.svg)
-->

## Results

**Held-out set (pending):** numbers will land here from
`eval/baseline_heldout.json` once the held-out baseline is run.

| Metric | Held-out |
|---|---|
| Transaction F1 | _TBD_ |
| Header field accuracy | _TBD_ |
| Validation pass rate | _TBD_ |
| Error rate | _TBD_ |
| Mean cost / doc | _TBD_ |
| Mean latency / doc | _TBD_ |

**Bankstatemently Open Benchmark (pending):** third-party score via their
evaluation API — `scripts/run_bankstatemently.py --submit`.

A finding from building this: the AgamiAI/Indian-Bank-Statements dataset
(our primary corpus) has internally inconsistent running balances in ~12% of
transaction rows — in both the ground-truth JSON *and* the rendered PDFs.
The validation layer caught it immediately (see `docs/DATA-REVIEW.md`).
That's the point of validating extractions instead of trusting them.

## Architecture

```
                    ┌─────────────┐
      PDF ────────► │  triage.py  │  text layer ≥100 chars?
                    └──────┬──────┘
              native ┌─────┴─────┐ scanned / unknown layout
                     ▼           ▼
            ┌───────────────┐  ┌────────────────────────┐
            │ parsers/      │  │ parsers/vision.py      │
            │ native.py     │  │ Gemini 2.5 Flash       │
            │ (pdfplumber)  │  │ via OpenRouter         │
            └───────┬───────┘  └───────────┬────────────┘
                    └─────────┬────────────┘
                              ▼
                    StatementDoc (pydantic, Decimal money)
                              ▼
                    ┌──────────────────┐
                    │   validate.py    │  balance continuity,
                    │  (never raises)  │  running balances,
                    └──────────────────┘  date sanity
```

## Quickstart

```bash
uv sync --dev
uv run pytest                                   # 32 tests, offline

# generate synthetic statements (PDF + ground-truth JSON)
uv run python -m datagen.generate --count 10 --out data/generated --seed 42 --scan

# run the offline eval (native path only)
uv run python -m eval.run_eval --manifest tests/fixtures/ci_manifest.jsonl --no-vision

# live vision path (scanned PDFs)
export OPENROUTER_API_KEY=sk-or-...
uv run python scripts/vision_smoke.py

# demo
uv run python app.py
```

## Demo

HF Space: _pending deploy_ — two tabs: precomputed samples (zero API cost)
and a rate-limited live upload (max 5 pages / 10 MB).

## Cost

Scanned statements run ~$0.005–0.02 each with Gemini 2.5 Flash
($0.30/M input, $2.50/M output tokens); native-text PDFs cost nothing.

## Eval

Custom harness (`eval/run_eval.py`): per-field header accuracy, transaction
P/R/F1 (date+amount exact, fuzzy description), validation pass rate, cost and
latency per doc.

Honesty note on the native path: `parsers/native.py` targets datagen's
template A **by design** (native parsers are per-layout), so its accuracy on
template-A docs measures multi-page/table handling, not layout generalization.
Datagen's template B (different labels, DD/MM/YYYY dates, Indian lakh digit
grouping) is deliberately *not* native-parseable — it exercises the
triage → vision fallback, and layout generalization is measured on the vision
path against AgamiAI docs and template-B docs. `eval/compare.py` is the CI regression gate — the build fails
if txn F1, header accuracy, or validation pass rate drop >0.01 below the
committed baseline.
