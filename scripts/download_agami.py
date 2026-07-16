"""Bulk-download paired Agami statements: both digital+scanned forms per ID."""
from __future__ import annotations

import argparse

from huggingface_hub import snapshot_download

REPO = "AgamiAI/Indian-Bank-Statements"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=25,
                    help="unique statement IDs per type (each = 2 PDFs + 2 JSONs)")
    args = ap.parse_args()
    patterns = [
        f"train/India_Bank_Statement_{form}_{t}/{i:05d}.*"
        for t in ("Type1", "Type2")
        for form in ("Digital", "Scanned")
        for i in range(1, args.per_type + 1)
    ]
    snapshot_download(REPO, repo_type="dataset", local_dir="data/agami_raw",
                      allow_patterns=patterns)
    print(f"downloaded {args.per_type} IDs x 2 types x 2 forms")


if __name__ == "__main__":
    main()
