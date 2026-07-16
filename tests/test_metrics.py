from datetime import date
from decimal import Decimal

from docval.schema import StatementDoc, Transaction
from eval.metrics import header_accuracy, match_transactions, transaction_prf


def txn(day, desc, amount, credit=False):
    kw = {"credit": Decimal(amount)} if credit else {"debit": Decimal(amount)}
    return Transaction(txn_date=date(2026, 1, day), description=desc, **kw)


def test_perfect_match():
    gold = [txn(5, "ATM WDL", "100.00"), txn(7, "NEFT/SALARY", "500.00", credit=True)]
    pred = [txn(5, "ATM WDL", "100.00"), txn(7, "NEFT/SALARY", "500.00", credit=True)]
    m = transaction_prf(pred, gold)
    assert m["precision"] == m["recall"] == m["f1"] == 1.0


def test_missed_and_spurious_rows():
    gold = [txn(5, "ATM WDL", "100.00"), txn(7, "NEFT/SALARY", "500.00", credit=True)]
    pred = [txn(5, "ATM WDL", "100.00"), txn(9, "GHOST ROW", "1.00")]
    m = transaction_prf(pred, gold)
    assert m["n_matched"] == 1
    assert m["precision"] == 0.5 and m["recall"] == 0.5


def test_fuzzy_description_still_matches():
    gold = [txn(5, "ATM WDL CONNAUGHT PL", "100.00")]
    pred = [txn(5, "ATM WDL CONNAUGHT", "100.00")]
    assert match_transactions(pred, gold) == [(0, 0)]


def test_amount_mismatch_never_matches():
    gold = [txn(5, "ATM WDL", "100.00")]
    pred = [txn(5, "ATM WDL", "100.01")]
    assert match_transactions(pred, gold) == []


def test_header_accuracy_flags_each_field():
    kw = dict(account_number="1", currency="INR", period_start=date(2026, 1, 1),
              period_end=date(2026, 1, 31), opening_balance=Decimal("1"),
              closing_balance=Decimal("1"), transactions=[])
    gold = StatementDoc(bank_name="Meridian Bank", **kw)
    pred = StatementDoc(bank_name="meridian bank", **(kw | {"currency": "USD"}))
    acc = header_accuracy(pred, gold)
    assert acc["bank_name"] is True      # case-insensitive
    assert acc["currency"] is False
    assert acc["opening_balance"] is True
