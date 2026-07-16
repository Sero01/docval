"""Synthetic bank-statement generator: PDF + ground-truth JSON pairs."""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from docval.schema import StatementDoc, Transaction

BANKS = ["Meridian Bank", "Cauvery National Bank", "Harborview Bank"]
DESCRIPTIONS = ["UPI/CRED/PAYMENT", "NEFT/SALARY/ACME LTD", "ATM WDL CONNAUGHT PL",
                "POS/GROCERY MART", "IMPS/TRANSFER/9821", "CHEQUE DEPOSIT 004512",
                "SERVICE CHARGE"]


def money(d: Decimal | None) -> str:
    return f"{d:,.2f}" if d is not None else ""


def build_statement(rng: random.Random) -> StatementDoc:
    opening = Decimal(rng.randrange(100_000, 50_000_000)) / 100
    start = date(2026, rng.randint(1, 6), 1)
    end = start + timedelta(days=29)
    balance = opening
    txns: list[Transaction] = []
    day = start
    for _ in range(rng.randint(8, 25)):
        day = min(day + timedelta(days=rng.randint(0, 3)), end)
        amount = Decimal(rng.randrange(100, 5_000_000)) / 100
        if rng.random() < 0.55 and balance - amount > 0:
            debit, credit = amount, None
            balance -= amount
        else:
            debit, credit = None, amount
            balance += amount
        txns.append(Transaction(txn_date=day, description=rng.choice(DESCRIPTIONS),
                                debit=debit, credit=credit, running_balance=balance))
    return StatementDoc(
        bank_name=rng.choice(BANKS),
        account_number=str(rng.randrange(10**11, 10**12)),
        currency="INR", period_start=start, period_end=end,
        opening_balance=opening, closing_balance=balance, transactions=txns)


def render_pdf(doc: StatementDoc, out_pdf: Path) -> None:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"))
    env.globals["money"] = money
    html = env.get_template("bank_a.html").render(doc=doc)
    HTML(string=html).write_pdf(str(out_pdf))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scan", action="store_true",
                    help="also emit scan-noise image variants")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for i in range(args.count):
        doc = build_statement(random.Random(args.seed + i))
        stem = args.out / f"stmt_{i:04d}"
        render_pdf(doc, stem.with_suffix(".pdf"))
        stem.with_suffix(".json").write_text(doc.model_dump_json(indent=2))
        if args.scan:
            from datagen.scanify import make_scan_variant
            make_scan_variant(stem.with_suffix(".pdf"),
                              args.out / f"stmt_{i:04d}_scan.pdf")
    print(f"wrote {args.count} statements to {args.out}")


if __name__ == "__main__":
    main()
