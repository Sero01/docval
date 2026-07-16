"""Run the pipeline over a manifest and write timestamped results.json."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from docval.config import VISION_MODEL
from docval.pipeline import extract
from docval.schema import StatementDoc
from docval.validate import Severity
from eval.metrics import HEADER_FIELDS, header_accuracy, transaction_prf


def evaluate(manifest: Path, allow_vision: bool) -> dict:
    per_doc = []
    for line in manifest.read_text().splitlines():
        entry = json.loads(line)
        gold = StatementDoc.model_validate_json(Path(entry["gold"]).read_text())
        result = extract(Path(entry["pdf"]), allow_vision=allow_vision)
        row: dict = {"pdf": entry["pdf"], "route": result.route,
                     "source": entry["source"]}
        if result.route == "error":
            row["error"] = result.error
        else:
            prf = transaction_prf(result.doc.transactions, gold.transactions)
            header = header_accuracy(result.doc, gold)
            row |= prf
            row["header_ok"] = sum(header.values()) / len(HEADER_FIELDS)
            row["validation_pass"] = result.report.overall == Severity.PASS
            if result.usage:
                row["cost_usd"] = result.usage.cost_usd
                row["latency_s"] = result.usage.latency_s
        per_doc.append(row)

    scored = [r for r in per_doc if "error" not in r]

    def mean(key: str) -> float:
        vals = [r[key] for r in scored if key in r]
        return sum(vals) / len(vals) if vals else 0.0

    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": VISION_MODEL, "manifest": str(manifest), "n_docs": len(per_doc),
        "aggregates": {
            "txn_precision": mean("precision"), "txn_recall": mean("recall"),
            "txn_f1": mean("f1"), "header_field_accuracy": mean("header_ok"),
            "validation_pass_rate": mean("validation_pass"),
            "error_rate": 1 - (len(scored) / len(per_doc) if per_doc else 1),
            "mean_cost_usd": mean("cost_usd"), "mean_latency_s": mean("latency_s"),
        },
        "per_doc": per_doc,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("eval/results"))
    ap.add_argument("--no-vision", action="store_true")
    args = ap.parse_args()
    results = evaluate(args.manifest, allow_vision=not args.no_vision)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = results["timestamp"].replace(":", "-")
    out_file = args.out / f"{stamp}.json"
    out_file.write_text(json.dumps(results, indent=2))
    print(json.dumps(results["aggregates"], indent=2))
    print("wrote", out_file)


if __name__ == "__main__":
    main()
