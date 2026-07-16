"""Deterministic extraction from text-layer PDFs (datagen layouts)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber

from docval.schema import StatementDoc, Transaction


class UnsupportedLayoutError(Exception):
    """Layout not recognized; caller should fall back to the vision path."""


_HEADER = {
    "account_number": re.compile(r"Account Number:\s*(\d+)"),
    "currency": re.compile(r"Currency:\s*([A-Z]{3})"),
    "period": re.compile(r"Statement Period:\s*(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})"),
    "opening": re.compile(r"Opening Balance:\s*([\d,]+\.\d{2})"),
    "closing": re.compile(r"Closing Balance:\s*([\d,]+\.\d{2})"),
}


def _dec(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def parse_native(pdf_path: Path) -> StatementDoc:
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        rows = [r for p in pdf.pages for r in (p.extract_table() or [])]
    matches = {name: pat.search(text) for name, pat in _HEADER.items()}
    missing = [name for name, m in matches.items() if m is None]
    if missing:
        raise UnsupportedLayoutError(f"header fields not found: {missing}")

    transactions = []
    headers: list[str] | None = None
    for row in rows:
        if not row or row[0] in (None, ""):
            continue
        if row[0] == "Date":
            headers = [c.strip() for c in row]
            continue
        txn_date, description, debit, credit, balance = row
        transactions.append(Transaction(
            txn_date=date.fromisoformat(txn_date.strip()),
            description=description.strip(),
            debit=_dec(debit) if debit else None,
            credit=_dec(credit) if credit else None,
            running_balance=_dec(balance) if balance else None,
            original=dict(zip(headers, (c or "" for c in row)))
            if headers else None))

    return StatementDoc(
        bank_name=text.splitlines()[0].strip(),
        account_number=matches["account_number"].group(1),
        currency=matches["currency"].group(1),
        period_start=date.fromisoformat(matches["period"].group(1)),
        period_end=date.fromisoformat(matches["period"].group(2)),
        opening_balance=_dec(matches["opening"].group(1)),
        closing_balance=_dec(matches["closing"].group(1)),
        transactions=transactions)
