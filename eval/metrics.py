"""Accuracy metrics: transaction alignment + header field accuracy."""
from __future__ import annotations

from difflib import SequenceMatcher

from docval.schema import StatementDoc, Transaction

HEADER_FIELDS = ("bank_name", "account_number", "currency", "period_start",
                 "period_end", "opening_balance", "closing_balance")


def _desc_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def match_transactions(pred: list[Transaction], gold: list[Transaction],
                       desc_threshold: float = 0.6) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    used_pred: set[int] = set()
    for gi, g in enumerate(gold):
        candidates = [
            (pi, _desc_sim(p.description, g.description))
            for pi, p in enumerate(pred)
            if pi not in used_pred
            and p.txn_date == g.txn_date
            and p.signed_amount == g.signed_amount]
        candidates = [(pi, sim) for pi, sim in candidates if sim >= desc_threshold]
        if candidates:
            best = max(candidates, key=lambda c: c[1])[0]
            used_pred.add(best)
            pairs.append((best, gi))
    return pairs


def transaction_prf(pred: list[Transaction], gold: list[Transaction]) -> dict:
    n_matched = len(match_transactions(pred, gold))
    precision = n_matched / len(pred) if pred else 0.0
    recall = n_matched / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else 0.0)
    return {"precision": precision, "recall": recall, "f1": f1,
            "n_pred": len(pred), "n_gold": len(gold), "n_matched": n_matched}


def header_accuracy(pred: StatementDoc, gold: StatementDoc) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for field in HEADER_FIELDS:
        p, g = getattr(pred, field), getattr(gold, field)
        if field == "bank_name":
            out[field] = p.strip().lower() == g.strip().lower()
        else:
            out[field] = p == g
    return out
