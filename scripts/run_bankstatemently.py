"""Run DocVal over the Bankstatemently benchmark statements and emit
per-statement extraction JSON for submission to their scoring API.

Their submission schema (README, verified 2026-07-16): POST
https://api.bankstatemently.com/v1/benchmark/evaluate with X-API-Key
(free key from bankstatemently.com/developers) and body
{"contentHash": <sha256 of pdf>, "transactions": [{"date": ISO,
"description": str, "amount": positive number, "direction":
"debit"|"credit", "balance": number}]}.

Usage:
  OPENROUTER_API_KEY=... uv run python scripts/run_bankstatemently.py
  ... BANKSTATEMENTLY_API_KEY=bsk_... uv run python scripts/run_bankstatemently.py --submit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from docval.pipeline import extract
from docval.schema import StatementDoc

BENCH = Path("data/bankstatemently")
OUT = Path("data/bankstatemently_out")
API_URL = "https://api.bankstatemently.com/v1/benchmark/evaluate"


def to_submission(doc: StatementDoc, pdf: Path) -> dict:
    txns = []
    for t in doc.transactions:
        row: dict = {
            "date": t.txn_date.isoformat(),
            "description": t.description,
            # zero-effect informational rows have neither debit nor credit
            "amount": float(abs(t.signed_amount)),
            "originalData": t.original or {
                "Date": t.txn_date.isoformat(),
                "Description": t.description,
                "Debit": str(t.debit) if t.debit is not None else "",
                "Credit": str(t.credit) if t.credit is not None else "",
                "Balance": (str(t.running_balance)
                            if t.running_balance is not None else ""),
            },
        }
        if t.debit is not None or t.credit is not None:
            row["direction"] = "debit" if t.debit is not None else "credit"
        if t.running_balance is not None:
            row["balance"] = float(t.running_balance)
        txns.append(row)
    return {"contentHash": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "transactions": txns}


def submit(payload: dict, api_key: str) -> dict:
    import httpx

    resp = httpx.post(API_URL, json=payload, timeout=120,
                      headers={"X-API-Key": api_key})
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true",
                    help="also POST each result to the scoring API")
    args = ap.parse_args()
    api_key = os.environ.get("BANKSTATEMENTLY_API_KEY")
    if args.submit and not api_key:
        raise SystemExit("--submit requires BANKSTATEMENTLY_API_KEY")

    OUT.mkdir(parents=True, exist_ok=True)
    total_cost = 0.0
    for pdf in sorted(BENCH.rglob("*.pdf")):
        result = extract(pdf)
        out = OUT / f"{pdf.stem}.json"
        if result.doc is None:
            out.write_text(json.dumps({"error": result.error}))
            print(f"{pdf.name}: ERROR {result.error}")
            continue
        payload = to_submission(result.doc, pdf)
        out.write_text(json.dumps(payload, indent=2))
        if result.usage:
            total_cost += result.usage.cost_usd
        print(f"{pdf.name}: {result.route}, validation "
              f"{result.report.overall.value}")
        if args.submit:
            score = submit(payload, api_key)
            (OUT / f"{pdf.stem}.score.json").write_text(json.dumps(score, indent=2))
            print(f"  score: overall parsed={score['parsedScore']['overall']} "
                  f"normalized={score['normalizedScore']['overall']}")
    print(f"total cost: ${total_cost:.2f}")


if __name__ == "__main__":
    main()
