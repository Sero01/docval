# AgamiAI/Indian-Bank-Statements — Dataset Quality Review

Audited 2026-07-16 on a 28-statement sample (25 Digital_Type1 + 1 each of
Digital_Type2, Scanned_Type1, Scanned_Type2). All values below are observed,
not guessed.

## Repo layout

```
train/India_Bank_Statement_Digital_Type1/  100 pdf + 100 json
train/India_Bank_Statement_Digital_Type2/  100 pdf + 100 json
train/India_Bank_Statement_Scanned_Type1/  100 pdf + 100 json
train/India_Bank_Statement_Scanned_Type2/  100 pdf + 100 json
```

- 802 files total: 400 PDFs + 400 JSONs, paired by shared stem
  (`00001.pdf` ↔ `00001.json`) in the same directory.
- **The dataset card's "10K<n<100K" size tag is wrong for our purposes — there
  are only 400 pairs** (the tag possibly counts transactions). Earlier notes
  saying "10K+ PDFs" are corrected by this review.
- **Scanned_TypeN is a pixel render of Digital_TypeN with byte-identical JSON**
  (verified by hash: Digital_Type1/00001 == Scanned_Type1/00001). So there are
  only **200 unique statements**, each in a native and a scanned form.
  ⚠️ Split-curation rule: the digital and scanned twins of the same statement
  must land in the SAME split, or we leak dev into held-out.

## PDF form

- All sampled PDFs are 6 pages, ~160 transactions per statement (quarterly
  business statements, Jan–Mar 2024).
- **Digital**: real text layer (~2.4–2.5K chars on page 1), BUT a diagonal
  "SYNTHETIC DATA - MACHINE GENERATED" watermark is itself text and pollutes
  extraction — `extract_text()` interleaves watermark letters mid-word
  ("Progressive NEational Bank E"), and `extract_tables()` cells contain
  stray fragments ("Rs. 38,0 87.63", "C T IRs. 2,574.63"). A native parser
  needs watermark filtering (e.g. drop chars by rotation/position) — doable
  with pdfplumber char-level filtering, but not free.
- **Scanned**: no text layer at all (0 chars) → vision path, as expected.
  Visual quality is good: realistic gray scan texture, same layout as digital.
- Visual check (digital + scanned 00001): plausible, professional Indian bank
  statement layout; header block + 8-column txn table; visible numbers match
  the paired JSON exactly (spot-checked ~30 rows including the header).

## JSON ground truth — two different schemas

Header (both types, top-level keys):
`account_holder, account_holder_address, account_number, account_type,
bank_name, branch_code, branch_name, branch_phone, closing_balance, currency,
customer_id, end_date, ifsc_code, interest_rate, micr_code, opening_balance,
start_date, statement_date, transactions`

Mapping to `StatementDoc`: `start_date`→`period_start`, `end_date`→`period_end`;
rest are 1:1 or extra (ignored).

**Type1 transaction** (Digital/Scanned_Type1):

```json
{"date": "2024-01-02 12:44:20", "value_date": "2024-01-02",
 "description": "Chq Paid-MICR Inward Clearing-KAUSHIK SAHA-HDFC BANK LTD.",
 "cheque_no": "567302", "debit": 23702.04, "credit": null,
 "balance": 41516.31, "branch_code": "3421", "failed": false}
```

**Type2 transaction** (Digital/Scanned_Type2) — different fields AND date format:

```json
{"transaction_id": "S85388609", "date": "01/01/2024", "value_date": "01/01/2024",
 "txn_posted_date": "01/01/2024 12:12:52 PM", "cheque_no": "-",
 "description": "RTGS-ICICR510742914335-Lakshmi Naidu", "cr_dr": "DR",
 "transaction_amount": 475617.41, "available_balance": 803454.76,
 "branch_code": "4156", "failed": false}
```

Amounts are JSON **floats** (2dp) — convert via `Decimal(str(x))`.
`failed: true` rows exist (~1 per statement) and do **not** move the balance;
they appear as reversal-style rows.

## Internal-consistency audit (the big finding)

Per-row check: `balance[i] == balance[i-1] ± amount[i]` (failed rows: balance
must not move).

- **0 of 28 files have a fully consistent chain.**
- **543 of 4,535 rows (12.0%) break the chain**, with jumps unexplained by any
  visible transaction (e.g. 00001 row 19: expected 28,601.09, actual 20,386.59).
- `last txn balance == closing_balance`: **28/28** — the endpoints agree; the
  breaks are *inside* the chain, as if the generator computed balances first
  and then silently dropped ~12% of rows.
- **The PDFs faithfully show the same broken balances** (checked 00001 around
  rows 19–20 in the rendered table) — so extraction ground truth is still
  valid: what's in the JSON is exactly what's on the page.
- The dataset card claims "proper debit/credit flows with accurate balance
  calculations" — that claim is false at the row level.

## Weirdness list

- ~12% hidden balance jumps (above) — generator bug, present in both PDF and JSON.
- `statement_date` is often *after* `end_date` by >1 year (e.g. period ends
  2024-03-31, statement_date 2025-11-22) — harmless.
- Two txn schemas + two date formats across types (conversion must branch).
- Watermark text layer pollution on Digital types (above).
- No weird dates/duplicate statements found beyond the digital/scanned twinning.

## Recommendation: **use partially, with eyes open**

1. **Use as primary extraction corpus** — 400 docs, gold JSON provably matches
   pixels, Apache 2.0, realistic Indian layouts. Extraction metrics
   (per-field accuracy, txn P/R/F1) are fully trustworthy.
2. **But it cannot demonstrate a clean `validation_pass_rate`**: our
   balance-continuity/running-balance checks will legitimately FAIL ~all Agami
   docs because the *source statements* are internally inconsistent. That's
   the validator working as designed (it catches the generator's bug — good
   demo story!), but we need datagen docs for the "consistent statement passes
   validation" half of the story. → Keep datagen in scope (it was already the
   native-path source; it's now also the only clean-validation source).
3. **Split rule**: pair digital+scanned twins into the same split.
4. Native parser on Agami Digital types needs watermark filtering; treat that
   as stretch scope — the datagen layouts remain the native parser's primary
   target (per plan), and Agami Digital can route to vision if not done.

**Decision needed from Parvez: go / no-go on the above before Task 9
(split curation). Tasks 4–8 proceed regardless (plan-approved).**
