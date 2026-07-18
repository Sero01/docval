# DocVal

Bank-statement extraction + validation pipeline. Extracts statements to
structured JSON (native text-layer parsing when possible, Gemini 2.5
Flash-Lite vision via OpenRouter for scans), then **validates the
arithmetic** — balance
continuity is the star check: does opening balance + every transaction really
equal the closing balance?

![ci](https://github.com/Sero01/docval/actions/workflows/ci.yml/badge.svg)

## Results

**Held-out set** (100 docs: 58 real AgamiAI statements + 42 synthetic,
gemini-2.5-flash-lite; full per-doc results in `eval/baseline_heldout.json`):

| Metric | Held-out | (prev baseline) |
|---|---|---|
| Transaction F1 | **0.63** | 0.51 |
| — real AgamiAI statements | **0.42** | 0.12 |
| — synthetic (datagen) | **0.92** | 0.92 |
| Header field accuracy | 0.87 | 0.89 |
| Validation pass rate | 0.25 | 0.26 |
| Error rate | **1%** | 13% |
| Mean cost / doc | $0.008 | $0.005 |
| Mean latency / doc | 70.9 s | 68.5 s |

The jump from the previous baseline comes from one change: per-page
extraction fallback for dense statements. Whole-document extraction of dense
multi-page scans blew past the 32k output-token cap or collapsed rows across
pages; splitting those docs into per-page calls cut the error rate from 13%
to 1% (the one remaining failure is a statement where the model persistently
emits malformed decimals that schema validation rejects) and took
real-statement F1 from 0.12 to 0.42, at ~1.6× the per-doc cost.

The by-source gap is still the honest finding: flash-lite reads clean
synthetic pages at F1 0.92 but garbles dense real statements (row shifts
across columns, debit/credit swaps, digit misreads) down to 0.42 — and the
validation layer flags exactly that (pass rate 0.25) rather than silently
accepting it.

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
            │ native.py     │  │ Gemini 2.5 Flash-Lite  │
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
uv run pytest                                   # 51 tests, offline

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

Live demo: **[docval-yy4s.onrender.com](https://docval-yy4s.onrender.com)** —
two tabs: precomputed samples (zero API cost) and a rate-limited live upload
(max 5 pages / 10 MB). Hosted on Render's free tier (HF paywalled Gradio
Spaces), so the first visit after an idle spell takes ~1 min to wake.

Sister project: **[ReconMatch](https://github.com/Sero01/reconmatch)**
([live demo](https://reconmatch-aa9c.onrender.com)) reconciles DocVal's
extracted statement lines against an internal ledger — matching, confidence
scores, and break classification.

## Cost

Scanned statements run well under a cent each with the default
Gemini 2.5 Flash-Lite ($0.10/M input, $0.40/M output tokens);
native-text PDFs cost nothing. Set `DOCVAL_VISION_MODEL` to switch
models (pricing table in `src/docval/config.py`).

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
