"""Download a sample of AgamiAI/Indian-Bank-Statements and audit its quality."""
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from huggingface_hub import list_repo_files, hf_hub_download

REPO = "AgamiAI/Indian-Bank-Statements"
OUT = Path("data/agami_raw")


def discover() -> list[str]:
    files = list_repo_files(REPO, repo_type="dataset")
    by_ext = Counter(Path(f).suffix for f in files)
    print(f"{len(files)} files. By extension: {dict(by_ext)}")
    for f in files[:30]:
        print(" ", f)
    return files


def download_sample(files: list[str], n: int = 25) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    picked = [f for f in files if Path(f).suffix in {".pdf", ".json"}][: n * 2]
    for f in picked:
        hf_hub_download(REPO, f, repo_type="dataset", local_dir=OUT)
    print(f"downloaded {len(picked)} files to {OUT}")


def audit_json() -> None:
    """For every ground-truth JSON: check internal arithmetic.

    Real field names (verified 2026-07-16). Header: opening_balance,
    closing_balance, start_date, end_date. Two txn schemas:
      Type1: debit/credit/balance, date "YYYY-MM-DD HH:MM:SS"
      Type2: cr_dr ("DR"/"CR")/transaction_amount/available_balance,
             date "DD/MM/YYYY"
    Failed txns do not move the balance.
    """
    full_ok, chain_break_files, last_eq_closing = 0, 0, 0
    total_breaks = total_rows = 0
    n = 0
    for p in sorted(OUT.rglob("*.json")):
        rec = json.loads(p.read_text())
        if n == 0:
            print("top-level keys:", sorted(rec.keys()))
        n += 1
        try:
            txns = rec["transactions"]
            opening = Decimal(str(rec["opening_balance"]))
            closing = Decimal(str(rec["closing_balance"]))
            bal, breaks = opening, 0
            for t in txns:
                if "cr_dr" in t:  # Type2 schema
                    amount = Decimal(str(t["transaction_amount"]))
                    amt = amount if t["cr_dr"] == "CR" else -amount
                    actual = Decimal(str(t["available_balance"]))
                else:  # Type1 schema
                    amt = Decimal(str(t["credit"] or 0)) - Decimal(str(t["debit"] or 0))
                    actual = Decimal(str(t["balance"]))
                expected = bal if t["failed"] else bal + amt
                if actual != expected:
                    breaks += 1
                bal = actual
            total_breaks += breaks
            total_rows += len(txns)
            if breaks == 0:
                full_ok += 1
            else:
                chain_break_files += 1
            last_bal = Decimal(str(txns[-1].get("balance",
                               txns[-1].get("available_balance")))) if txns else None
            if last_bal == closing:
                last_eq_closing += 1
        except (InvalidOperation, TypeError, KeyError) as e:
            print(f"  {p.name}: cannot audit ({e})")
    print(f"{n} files: fully consistent chain: {full_ok}, "
          f"files with chain breaks: {chain_break_files}")
    print(f"broken rows: {total_breaks}/{total_rows} "
          f"({100 * total_breaks / max(total_rows, 1):.1f}%)")
    print(f"last txn balance == closing_balance: {last_eq_closing}/{n}")


if __name__ == "__main__":
    files = discover()
    download_sample(files)
    audit_json()
