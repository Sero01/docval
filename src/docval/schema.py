"""Single data contract for DocVal. All parsers emit StatementDoc."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator


class Transaction(BaseModel):
    txn_date: date
    description: str
    debit: Decimal | None = None
    credit: Decimal | None = None
    running_balance: Decimal | None = None

    @model_validator(mode="after")
    def at_most_one_amount(self) -> Self:
        # Both None is a zero-effect informational row (e.g. a printed
        # failed-transaction line); both set is contradictory.
        if self.debit is not None and self.credit is not None:
            raise ValueError("at most one of debit or credit may be set")
        return self

    @property
    def signed_amount(self) -> Decimal:
        if self.credit is not None:
            return self.credit
        if self.debit is not None:
            return -self.debit
        return Decimal("0")


class UsageStats(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0


class StatementDoc(BaseModel):
    bank_name: str
    account_number: str
    currency: str = Field(min_length=3, max_length=3)
    period_start: date
    period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    transactions: list[Transaction] = Field(default_factory=list)
