import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

from docval.schema import StatementDoc, Transaction

_spec = importlib.util.spec_from_file_location(
    "run_bankstatemently",
    Path(__file__).parent.parent / "scripts" / "run_bankstatemently.py")
run_bankstatemently = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_bankstatemently)
to_submission = run_bankstatemently.to_submission


def _doc(transactions: list[Transaction]) -> StatementDoc:
    return StatementDoc(
        bank_name="Meridian Bank", account_number="123456789012",
        currency="INR", period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31), opening_balance=Decimal("1000.00"),
        closing_balance=Decimal("900.00"), transactions=transactions)


def _pdf(tmp_path) -> Path:
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-fake")
    return pdf


def test_original_data_passed_through(tmp_path):
    original = {"Date": "05/01/2026", "Description": "ATM WDL",
                "Debit": "100.00", "Credit": "", "Balance": "900.00"}
    txn = Transaction(txn_date=date(2026, 1, 5), description="ATM WDL",
                      debit=Decimal("100.00"),
                      running_balance=Decimal("900.00"), original=original)
    payload = to_submission(_doc([txn]), _pdf(tmp_path))
    row = payload["transactions"][0]
    assert row["originalData"] == original
    assert row["amount"] == 100.0
    assert row["direction"] == "debit"
    assert row["balance"] == 900.0


def test_original_data_reconstructed_when_missing(tmp_path):
    # originalData is required by the API; fall back to canonical strings
    txn = Transaction(txn_date=date(2026, 1, 5), description="ATM WDL",
                      credit=Decimal("50.00"))
    payload = to_submission(_doc([txn]), _pdf(tmp_path))
    row = payload["transactions"][0]
    assert row["originalData"] == {"Date": "2026-01-05",
                                   "Description": "ATM WDL", "Debit": "",
                                   "Credit": "50.00", "Balance": ""}
    assert row["direction"] == "credit"
    assert "balance" not in row  # optional field, never null


def test_zero_effect_row_submitted_without_direction(tmp_path):
    # Informational rows (failed txns) have neither debit nor credit; the
    # old mapping crashed on float(None)
    txn = Transaction(txn_date=date(2026, 1, 6),
                      description="FAILED-INSUFFICIENT FUNDS")
    payload = to_submission(_doc([txn]), _pdf(tmp_path))
    row = payload["transactions"][0]
    assert row["amount"] == 0.0
    assert "direction" not in row
