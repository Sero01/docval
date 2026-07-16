from datetime import date
from decimal import Decimal

from docval.schema import StatementDoc, Transaction
from docval.validate import Severity, validate_statement


def make_doc(**kw) -> StatementDoc:
    txns = [
        Transaction(txn_date=date(2026, 1, 5), description="NEFT/SALARY",
                    credit=Decimal("500.00"), running_balance=Decimal("1500.00")),
        Transaction(txn_date=date(2026, 1, 10), description="ATM WDL",
                    debit=Decimal("200.00"), running_balance=Decimal("1300.00")),
    ]
    base = dict(bank_name="Meridian Bank", account_number="123456789012",
                currency="INR", period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31), opening_balance=Decimal("1000.00"),
                closing_balance=Decimal("1300.00"), transactions=txns)
    base.update(kw)
    return StatementDoc(**base)


def test_consistent_statement_passes():
    report = validate_statement(make_doc())
    assert report.overall == Severity.PASS


def test_broken_closing_balance_fails():
    report = validate_statement(make_doc(closing_balance=Decimal("9999.00")))
    assert report.overall == Severity.FAIL
    assert any(f.check == "balance_continuity" and f.severity == Severity.FAIL
               for f in report.findings)


def test_broken_running_balance_fails():
    doc = make_doc()
    doc.transactions[1].running_balance = Decimal("1.00")
    report = validate_statement(doc)
    assert any(f.check == "running_balance" and f.severity == Severity.FAIL
               for f in report.findings)


def test_txn_outside_period_fails():
    doc = make_doc()
    doc.transactions[0].txn_date = date(2026, 3, 1)
    report = validate_statement(doc)
    assert any(f.check == "date_in_period" and f.severity == Severity.FAIL
               for f in report.findings)


def test_unordered_dates_warn_only():
    doc = make_doc()
    doc.transactions[0].txn_date, doc.transactions[1].txn_date = (
        doc.transactions[1].txn_date, doc.transactions[0].txn_date)
    # keep balances consistent with swapped order irrelevant here; ordering is the point
    report = validate_statement(doc)
    assert any(f.check == "date_ordering" and f.severity == Severity.WARN
               for f in report.findings)
