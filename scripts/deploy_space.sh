#!/usr/bin/env bash
# Deploy the DocVal demo to the HF Space Sero01/docval.
#
# Needs: `hf auth login` done, and OPENROUTER_API_KEY exported (or in .env)
# for the live-upload tab's Space secret.
#
# Usage: bash scripts/deploy_space.sh
set -euo pipefail
cd "$(dirname "$0")/.."

SPACE=Sero01/docval
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

[ -f .env ] && set -a && source .env && set +a
: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY not set (needed as Space secret)}"

hf repo create docval --repo-type space --space_sdk gradio --exist-ok

cp -r app.py requirements.txt packages.txt pyproject.toml src datagen eval samples "$STAGE"/
find "$STAGE" -name __pycache__ -type d -exec rm -rf {} +
rm -rf "$STAGE"/eval/results

cat > "$STAGE"/README.md <<'EOF'
---
title: DocVal
emoji: 🏦
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 6.20.0
app_file: app.py
pinned: false
license: mit
short_description: Bank-statement extraction + validation demo
---

# DocVal

Extracts bank statements to structured JSON with Gemini 2.5 Flash-Lite
(via OpenRouter), then validates them — balance continuity, date sanity,
debit/credit consistency.

Two tabs:

- **Samples (precomputed)** — bundled synthetic statements with cached
  results, zero API cost.
- **Try your own (live)** — upload a PDF (max 5 pages / 10 MB),
  rate-limited.

Source: [github.com/Sero01/docval](https://github.com/Sero01/docval)
EOF

uv run python - <<'EOF'
import os
from huggingface_hub import HfApi
HfApi().add_space_secret("Sero01/docval", "OPENROUTER_API_KEY",
                         os.environ["OPENROUTER_API_KEY"])
print("Space secret OPENROUTER_API_KEY set")
EOF

hf upload "$SPACE" "$STAGE" . --repo-type space \
  --commit-message "Deploy DocVal demo (app + samples + pipeline)"
echo "Deployed: https://huggingface.co/spaces/$SPACE"
