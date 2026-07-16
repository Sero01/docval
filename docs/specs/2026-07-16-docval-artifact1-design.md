# DocVal — Artifact 1 Design: Bank-Statement Extraction & Validation Pipeline

**Date:** 2026-07-16
**Status:** Approved design, pending implementation plan
**Owner:** Parvez Ahmed

## Context

Artifact 1 of the Strategic Roadmap v3 (Phase 1, Weeks 1–4). Goal: convert private
enterprise experience (banking, reconciliation, ML) into public proof — one document
type done excellently, with accuracy numbers, a test suite, and a live URL.

Decisions made during brainstorming (2026-07-16):

- **Document type: bank statements** (not invoices). Differentiated, aligned with
  Parvez's TLM/banking moat, and partially recovers the narrative of the deprioritized
  Artifact 3 (statement extraction is the input side of reconciliation).
- **Approach: hybrid pipeline** — deterministic parsing for native PDFs, vision-LLM for
  scanned ones, shared schema, deterministic validation layer on top.
- **Model: `google/gemini-2.5-flash` via the OpenRouter API** ($0.30/M input, $2.50/M
  output; vision + structured outputs supported). At demo volume this is a few
  dollars/month. Optional stretch: a second-model comparison row (e.g. a Claude or
  Gemini Flash Lite) through the same OpenRouter client — one string change.
- **Hosting: Hugging Face Spaces + Gradio** (free, Python-native, doc-AI audience).
- Artifact 3 (recon-matching demo) is deprioritized; growth over revenue.

## Repository

New repo: `docval` (separate from parvez-roadmap). This spec moves into that repo when
it is scaffolded.

## Architecture

```
PDF in
  └─ Triage (pdfplumber): usable text layer?
       ├─ Native path  → deterministic parser (text + table extraction)
       └─ Scanned path → page → image (pypdfium2) → Gemini 2.5 Flash vision (OpenRouter)
                          → structured outputs, schema-enforced JSON
  Both paths emit the same Pydantic v2 model:
    StatementDoc { bank, account_meta, currency, period,
                   opening_balance, closing_balance,
                   transactions[ {date, description, debit|credit, running_balance?} ] }
  └─ Validation layer (pure functions over StatementDoc):
       • balance continuity: opening + Σ(txns) == closing; per-row running-balance chain
       • date sanity: within statement period, ordering
       • debit/credit sign consistency; currency & amount format checks
       • completeness: required fields present
  └─ Output: validated JSON + per-field validation report (pass / warn / fail tags)
```

### Modules (single responsibility each)

| Module | Responsibility |
|---|---|
| `triage.py` | Decide native vs scanned path |
| `parsers/native.py` | Deterministic extraction from text-layer PDFs |
| `parsers/vision.py` | Gemini 2.5 Flash vision extraction (OpenRouter) for scanned pages |
| `schema.py` | `StatementDoc` Pydantic model — the single contract between all parts |
| `validate.py` | All validation rules; never throws, always reports |
| `datagen/` | Synthetic statement generator (templates → PDF + ground-truth JSON) |
| `eval/` | Custom eval harness, metrics, regression compare |
| `app.py` | Gradio demo UI |

### Key API details (OpenRouter, verified 2026-07-16)

- Model string: `google/gemini-2.5-flash` via OpenRouter ($0.30/M in, $2.50/M out).
  Client: the `openai` Python SDK with `base_url="https://openrouter.ai/api/v1"` and
  `OPENROUTER_API_KEY` — OpenRouter is OpenAI-compatible.
- Structured outputs via `response_format={"type": "json_schema", "json_schema": ...}`
  generated from the `StatementDoc` Pydantic model (`model_json_schema()`); always
  re-validate the response with Pydantic — never trust the wire JSON blindly.
- Images as base64 `data:` URLs in `image_url` content blocks; keep scan renders at a
  DPI where text is legible (~150–200 DPI), downsample only if cost demands.
- Track the `usage` object per request for the cost/latency metrics.
- Model choice is a config value, not hardcoded — enables the comparison-row stretch
  and future model swaps without touching parser code.

## Data plan (existing datasets first, generator fills gaps)

- **Primary: `AgamiAI/Indian-Bank-Statements`** (Hugging Face, Apache 2.0, verified
  2026-07-16): tens of thousands of fully synthetic Indian business current-account
  statements as scanned PDFs + digital JSON ground truth (account meta, balances,
  transactions with UPI/NEFT/RTGS/IMPS types). No real PII. Week-1 task: download,
  inspect quality, and curate splits from it.
- **Splits**: ~50 dev docs (iterate freely), ~100 held-out eval docs (report numbers,
  never used for tuning), plus the **Bankstatemently Open Benchmark** (15 synthetic
  statements, 12 countries, 40 challenges, server-side ground truth + scoring API —
  github.com/bankstatemently/bank-statement-parsing-benchmark) as the third-party test.
- **Gap-filler: synthetic generator (`datagen/`)**, scoped down: Jinja2 HTML → PDF via
  WeasyPrint, only for what the HF dataset lacks — non-Indian layouts, personal
  accounts, native-text-layer PDFs (if the HF set is scan-only, the native-parser path
  needs these), and targeted edge cases. Ground-truth JSON alongside every PDF; scan
  variants via Pillow noise/rotation. First candidate for scope cuts.
- Week-1 hard gate: curated dev/eval splits exist by day 2; native parser extracting
  10 docs end-to-end by end of week 1.

## Eval harness (custom — RAGAS is RAG-specific, not applicable)

Metrics per run:

- **Header fields** (balances, period, account meta): exact-match accuracy per field.
- **Transactions**: align extracted vs ground-truth rows (date + amount, fuzzy
  description) → transaction-level precision / recall / F1; field-level accuracy
  within matched rows.
- **Validation pass rate**: % of docs passing balance-continuity and all checks.
- **Cost & latency per document** (from API `usage`).

Every run writes timestamped `results.json`; a compare script diffs against the stored
baseline and fails on regression. CI runs the regression gate on a small fixed subset.
Bankstatemently submission once the harness is stable.

## Demo (HF Spaces + Gradio)

- Bundled sample docs → pre-computed results (zero API cost for casual visitors).
- Upload path: rate-limited, size-capped (~5 pages), API key via HF Space secrets.
- Views: extracted transaction table; validation report with pass/warn/fail badges;
  metrics tab showing latest eval numbers.

## Error handling

- Triage failure → falls through to vision path.
- Vision/API errors → clean "extraction failed" state in UI and a typed error in the
  library API; never a stack trace to the user. Use the OpenAI SDK's typed exceptions
  (`openai.RateLimitError`, `openai.APIStatusError` etc.), most-specific-first.
- Validation never throws — it reports findings.
- Malformed/oversized uploads rejected at the boundary.

## Testing & CI

- pytest units: parsers, every validator rule individually.
- Golden-file tests: known PDF → expected `StatementDoc` JSON.
- GitHub Actions: tests + mini eval-regression check → green badge on README.

## Four-week plan

| Week | Deliverable | Hard constraint |
|---|---|---|
| 1 | HF dataset curated into dev/eval sets; `datagen/` covers gaps; native parser on 10 docs end-to-end | Test data must exist by end of week 1 |
| 2 | Vision path + full validation layer with error tagging | Cut templates, not validation quality |
| 3 | Eval harness, baseline metrics, regression tracking, Bankstatemently score | The numbers are the point |
| 4 | HF Space live, tests + CI green, README with numbers | Live URL is non-negotiable |

Scope cuts if behind, in order: shrink `datagen/` (fewer gap-filler templates) → drop
scanned-noise variants → drop the second-model comparison row. Never cut: validation
layer, eval harness.

## Success criteria

- Live HF Space URL that a stranger can click and use.
- Published per-field and transaction-level accuracy numbers on the held-out set.
- Third-party Bankstatemently score.
- GitHub repo with green Actions badge and a README that leads with the metrics.

## Verification

- Run the eval harness end-to-end on the held-out set; inspect `results.json`.
- Upload one native and one scanned PDF through the live Space; confirm extraction,
  validation report, and rate limiting behave.
- CI green on a fresh clone.
