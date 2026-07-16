from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from docval.schema import StatementDoc, Transaction


def make_txn(**kw):
    base = dict(txn_date=date(2026, 1, 5), description="UPI/PAYMENT",
                debit=Decimal("100.00"), credit=None, running_balance=None)
    base.update(kw)
    return Transaction(**base)


def test_debit_txn_signed_amount_is_negative():
    assert make_txn().signed_amount == Decimal("-100.00")


def test_credit_txn_signed_amount_is_positive():
    t = make_txn(debit=None, credit=Decimal("250.50"))
    assert t.signed_amount == Decimal("250.50")


def test_both_debit_and_credit_rejected():
    with pytest.raises(ValidationError):
        make_txn(credit=Decimal("1.00"))


def test_zero_effect_row_allowed_with_zero_signed_amount():
    # Real statements print amount-less informational rows (e.g. failed
    # transactions); they must be representable and must not move the balance.
    t = make_txn(debit=None, credit=None)
    assert t.signed_amount == Decimal("0")


def test_statement_parses_string_amounts_and_dates():
    doc = StatementDoc.model_validate({
        "bank_name": "Meridian Bank", "account_number": "123456789012",
        "currency": "INR", "period_start": "2026-01-01", "period_end": "2026-01-31",
        "opening_balance": "1000.00", "closing_balance": "900.00",
        "transactions": [{"txn_date": "2026-01-05", "description": "ATM WDL",
                          "debit": "100.00", "credit": None, "running_balance": "900.00"}],
    })
    assert doc.opening_balance == Decimal("1000.00")
    assert doc.transactions[0].txn_date == date(2026, 1, 5)
