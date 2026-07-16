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

_COUNTERPARTIES = ["ACME LTD", "SHARMA TRADERS", "GUPTA & SONS", "ZEPHYR TECH",
                   "RELIANCE FRESH", "BLUE DART", "K R ENTERPRISES", "OM SAI STORES",
                   "VERMA TEXTILES", "NATIONAL INSURANCE", "AIRTEL PREPAID",
                   "TATA POWER", "LIC PREMIUM", "SWIGGY", "INDIAN OIL"]
_PLACES = ["CONNAUGHT PL", "MG ROAD", "ANDHERI WEST", "SALT LAKE", "T NAGAR",
           "SECTOR 18 NOIDA", "KORAMANGALA"]


def money(d: Decimal | None) -> str:
    return f"{d:,.2f}" if d is not None else ""


def money_inr(d: Decimal | None) -> str:
    """Indian digit grouping: last 3 digits, then groups of 2 (1,23,45,678.90)."""
    if d is None:
        return ""
    sign = "-" if d < 0 else ""
    whole, frac = f"{abs(d):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        pairs = []
        while head:
            pairs.append(head[-2:])
            head = head[:-2]
        whole = ",".join(reversed(pairs)) + "," + tail
    return f"{sign}{whole}.{frac}"


def _description(rng: random.Random) -> str:
    kind = rng.random()
    if kind < 0.30:
        return f"UPI/{rng.choice(_COUNTERPARTIES)}/{rng.randrange(10**9, 10**10)}"
    if kind < 0.45:
        return f"NEFT/{rng.choice(_COUNTERPARTIES)}/N{rng.randrange(10**6, 10**7)}"
    if kind < 0.60:
        return f"IMPS/TRANSFER/{rng.randrange(10**7, 10**8)}"
    if kind < 0.75:
        return f"POS/{rng.choice(_COUNTERPARTIES)}"
    if kind < 0.85:
        return f"ATM WDL {rng.choice(_PLACES)}"
    if kind < 0.95:
        return f"CHEQUE DEPOSIT {rng.randrange(10**5, 10**6):06d}"
    return "SERVICE CHARGE"


def _amount(rng: random.Random, description: str) -> Decimal:
    if description == "SERVICE CHARGE":
        return Decimal(rng.randrange(1000, 60_000)) / 100  # small fees
    # log-normal-ish: many small payments, occasional large transfers
    raw = min(max(rng.lognormvariate(6.5, 1.4), 1.0), 2_000_000.0)
    return Decimal(f"{raw:.2f}")


def build_statement(rng: random.Random, min_txns: int = 8,
                    max_txns: int = 25) -> StatementDoc:
    opening = Decimal(rng.randrange(100_000, 50_000_000)) / 100
    start = date(2026, rng.randint(1, 6), 1)
    end = start + timedelta(days=29)
    balance = opening
    txns: list[Transaction] = []
    day = start
    for _ in range(rng.randint(min_txns, max_txns)):
        day = min(day + timedelta(days=rng.randint(0, 3)), end)
        description = _description(rng)
        amount = _amount(rng, description)
        if (description == "SERVICE CHARGE" or rng.random() < 0.55) \
                and balance - amount > 0:
            debit, credit = amount, None
            balance -= amount
        else:
            debit, credit = None, amount
            balance += amount
        txns.append(Transaction(txn_date=day, description=description,
                                debit=debit, credit=credit, running_balance=balance))
    return StatementDoc(
        bank_name=rng.choice(BANKS),
        account_number=str(rng.randrange(10**11, 10**12)),
        currency="INR", period_start=start, period_end=end,
        opening_balance=opening, closing_balance=balance, transactions=txns)


def render_pdf(doc: StatementDoc, out_pdf: Path,
               template: str = "bank_a.html") -> None:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"))
    env.globals["money"] = money
    env.globals["money_inr"] = money_inr
    env.globals["ddmmyyyy"] = lambda d: d.strftime("%d/%m/%Y")
    html = env.get_template(template).render(doc=doc)
    HTML(string=html).write_pdf(str(out_pdf))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scan", action="store_true",
                    help="also emit scan-noise image variants")
    ap.add_argument("--templates", default="a",
                    help="comma-separated template letters, assigned round-robin "
                         "(e.g. 'a,b'; template b is not native-parseable by design)")
    ap.add_argument("--big-frac", type=float, default=0.0,
                    help="fraction of statements rendered multi-page (90-110 txns)")
    args = ap.parse_args()
    templates = [f"bank_{t.strip()}.html" for t in args.templates.split(",")]
    args.out.mkdir(parents=True, exist_ok=True)
    for i in range(args.count):
        rng = random.Random(args.seed + i)
        big = rng.random() < args.big_frac
        doc = build_statement(rng, min_txns=90 if big else 8,
                              max_txns=110 if big else 25)
        stem = args.out / f"stmt_{i:04d}"
        render_pdf(doc, stem.with_suffix(".pdf"), template=templates[i % len(templates)])
        stem.with_suffix(".json").write_text(doc.model_dump_json(indent=2))
        if args.scan:
            from datagen.scanify import make_scan_variant
            make_scan_variant(stem.with_suffix(".pdf"),
                              args.out / f"stmt_{i:04d}_scan.pdf")
    print(f"wrote {args.count} statements to {args.out}")


if __name__ == "__main__":
    main()
