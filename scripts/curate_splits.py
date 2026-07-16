"""Convert AgamiAI records to StatementDoc gold JSON and write split manifests.

Field names are the observed values recorded in docs/DATA-REVIEW.md.
Split rule (DATA-REVIEW): the digital and scanned twins of one statement must
land in the SAME split, or dev leaks into held-out. The same applies to a
datagen statement's native and scan PDFs — splitting happens per statement
group, never per file.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from docval.parsers.native import UnsupportedLayoutError, parse_native
from docval.schema import StatementDoc

AGAMI_ROOT = Path("data/agami_raw/train")
GOLD_DIR = Path("data/gold")
DEV_SIZE, HELDOUT_SIZE = 50, 100


def _dec(x) -> Decimal:
    return Decimal(str(x))


def _txn_date(raw: str) -> date:
    raw = raw.strip()
    if "/" in raw:  # Type2: DD/MM/YYYY
        return datetime.strptime(raw, "%d/%m/%Y").date()
    return date.fromisoformat(raw.split(" ")[0])  # Type1: "YYYY-MM-DD HH:MM:SS"


def _convert_txn(t: dict) -> dict:
    if "cr_dr" in t:  # Type2 schema
        amount = _dec(t["transaction_amount"])
        is_debit = t["cr_dr"].upper() == "DR"
        debit, credit = (amount, None) if is_debit else (None, amount)
        balance = _dec(t["available_balance"])
    else:  # Type1 schema
        debit = _dec(t["debit"]) if t.get("debit") is not None else None
        credit = _dec(t["credit"]) if t.get("credit") is not None else None
        balance = _dec(t["balance"])
    return {"txn_date": _txn_date(t["date"]), "description": t["description"],
            "debit": debit, "credit": credit, "running_balance": balance}


def convert(record: dict) -> StatementDoc:
    return StatementDoc(
        bank_name=record["bank_name"],
        account_number=str(record["account_number"]),
        currency=record["currency"],
        period_start=date.fromisoformat(record["start_date"]),
        period_end=date.fromisoformat(record["end_date"]),
        opening_balance=_dec(record["opening_balance"]),
        closing_balance=_dec(record["closing_balance"]),
        transactions=[_convert_txn(t) for t in record["transactions"]],
    )


def agami_groups() -> list[list[dict]]:
    """One group per unique statement = [digital entry, scanned entry].

    The digital and scanned JSONs are byte-identical (DATA-REVIEW), so gold
    is converted once from the digital copy.
    """
    groups: list[list[dict]] = []
    for type_n in ("Type1", "Type2"):
        digital_dir = AGAMI_ROOT / f"India_Bank_Statement_Digital_{type_n}"
        for j in sorted(digital_dir.glob("*.json")):
            try:
                doc = convert(json.loads(j.read_text()))
            except Exception as e:
                print(f"SKIP {type_n}/{j.name}: {type(e).__name__}: {e}")
                continue
            gold = GOLD_DIR / f"agami_{type_n.lower()}_{j.stem}.json"
            gold.write_text(doc.model_dump_json(indent=2))
            group = [
                {"pdf": str(pdf), "gold": str(gold), "source": "agami",
                 "route_hint": "vision"}  # Agami layouts are not native-parseable
                for form in ("Digital", "Scanned")
                if (pdf := AGAMI_ROOT / f"India_Bank_Statement_{form}_{type_n}"
                    / f"{j.stem}.pdf").exists()
            ]
            if group:
                groups.append(group)
    return groups


def datagen_groups() -> list[list[dict]]:
    """One group per generated statement = [native-pdf entry, scan-pdf entry]."""
    groups: list[list[dict]] = []
    for j in sorted(Path("data/generated").glob("stmt_*.json")):
        group = []
        for pdf in (j.with_suffix(".pdf"), j.parent / f"{j.stem}_scan.pdf"):
            if not pdf.exists():
                continue
            try:  # honest hint: probe rather than assume the template
                parse_native(pdf)
                hint = "native"
            except (UnsupportedLayoutError, Exception):
                hint = "vision"
            group.append({"pdf": str(pdf), "gold": str(j),
                          "source": "datagen", "route_hint": hint})
        if group:
            groups.append(group)
    return groups


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    groups = agami_groups() + datagen_groups()
    rng = random.Random(42)
    rng.shuffle(groups)

    dev: list[dict] = []
    heldout: list[dict] = []
    for group in groups:
        if len(dev) < DEV_SIZE:
            dev.extend(group)
        elif len(heldout) < HELDOUT_SIZE:
            heldout.extend(group)

    for name, split in [("data/manifest_dev.jsonl", dev),
                        ("data/manifest_heldout.jsonl", heldout)]:
        Path(name).write_text("\n".join(json.dumps(e) for e in split) + "\n")

    def stats(split: list[dict]) -> str:
        by = lambda k, v: sum(1 for e in split if e[k] == v)  # noqa: E731
        return (f"{len(split)} entries (agami={by('source', 'agami')}, "
                f"datagen={by('source', 'datagen')}, "
                f"native-hint={by('route_hint', 'native')})")

    print("dev:    ", stats(dev))
    print("heldout:", stats(heldout))

    # endpoint sanity: converted gold must end where the statement says it ends
    bad = [g.name for g in sorted(GOLD_DIR.glob("agami_*.json"))
           if (d := StatementDoc.model_validate_json(g.read_text())).transactions
           and d.transactions[-1].running_balance != d.closing_balance]
    print(f"gold endpoint check: {len(bad)} of "
          f"{len(list(GOLD_DIR.glob('agami_*.json')))} mismatched", bad[:5])


if __name__ == "__main__":
    main()
