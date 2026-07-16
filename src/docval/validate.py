"""Deterministic validation of StatementDoc. Never raises - always reports."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from docval.schema import StatementDoc


class Severity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Finding(BaseModel):
    check: str
    severity: Severity
    message: str


class ValidationReport(BaseModel):
    findings: list[Finding]

    @property
    def overall(self) -> Severity:
        severities = {f.severity for f in self.findings}
        if Severity.FAIL in severities:
            return Severity.FAIL
        if Severity.WARN in severities:
            return Severity.WARN
        return Severity.PASS


def _ok(check: str, message: str) -> Finding:
    return Finding(check=check, severity=Severity.PASS, message=message)


def check_balance_continuity(doc: StatementDoc) -> list[Finding]:
    expected = doc.opening_balance + sum(
        (t.signed_amount for t in doc.transactions), Decimal("0"))
    if expected == doc.closing_balance:
        return [_ok("balance_continuity", "opening + transactions == closing")]
    return [Finding(check="balance_continuity", severity=Severity.FAIL,
                    message=f"expected closing {expected}, statement says {doc.closing_balance}")]


def check_running_balances(doc: StatementDoc) -> list[Finding]:
    findings: list[Finding] = []
    computed = doc.opening_balance
    for i, txn in enumerate(doc.transactions):
        computed += txn.signed_amount
        if txn.running_balance is not None and txn.running_balance != computed:
            findings.append(Finding(
                check="running_balance", severity=Severity.FAIL,
                message=f"row {i}: expected {computed}, got {txn.running_balance}"))
    return findings or [_ok("running_balance", "running balance chain consistent")]


def check_dates_in_period(doc: StatementDoc) -> list[Finding]:
    findings = [
        Finding(check="date_in_period", severity=Severity.FAIL,
                message=f"row {i}: {txn.txn_date} outside {doc.period_start}..{doc.period_end}")
        for i, txn in enumerate(doc.transactions)
        if not (doc.period_start <= txn.txn_date <= doc.period_end)
    ]
    return findings or [_ok("date_in_period", "all transaction dates within period")]


def check_date_ordering(doc: StatementDoc) -> list[Finding]:
    dates = [t.txn_date for t in doc.transactions]
    if dates != sorted(dates):
        return [Finding(check="date_ordering", severity=Severity.WARN,
                        message="transaction dates are not in ascending order")]
    return [_ok("date_ordering", "dates ascending")]


ALL_CHECKS = (check_balance_continuity, check_running_balances,
              check_dates_in_period, check_date_ordering)


def validate_statement(doc: StatementDoc) -> ValidationReport:
    findings: list[Finding] = []
    for check in ALL_CHECKS:
        findings.extend(check(doc))
    return ValidationReport(findings=findings)
