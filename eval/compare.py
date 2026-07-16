"""Compare an eval results file against a baseline; fail on regression."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TRACKED = ("txn_f1", "header_field_accuracy", "validation_pass_rate")


def regressions(new: dict, baseline: dict, tolerance: float = 0.01) -> list[str]:
    out = []
    for key in TRACKED:
        n, b = new["aggregates"][key], baseline["aggregates"][key]
        if n < b - tolerance:
            out.append(f"{key}: {n:.4f} < baseline {b:.4f} (tolerance {tolerance})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("new", type=Path)
    ap.add_argument("baseline", type=Path)
    ap.add_argument("--tolerance", type=float, default=0.01)
    args = ap.parse_args()
    regs = regressions(json.loads(args.new.read_text()),
                       json.loads(args.baseline.read_text()), args.tolerance)
    for r in regs:
        print("REGRESSION:", r)
    if regs:
        sys.exit(1)
    print("no regressions")


if __name__ == "__main__":
    main()
