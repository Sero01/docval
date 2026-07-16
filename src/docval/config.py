"""Runtime configuration. Model choice is config, never hardcoded in parsers."""
from __future__ import annotations

import os

from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# $ per 1M tokens (input, output), per OpenRouter listing
MODEL_PRICES = {
    "google/gemini-2.5-flash": (0.30, 2.50),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
}

VISION_MODEL = os.environ.get("DOCVAL_VISION_MODEL", "google/gemini-2.5-flash-lite")
if VISION_MODEL not in MODEL_PRICES:
    raise RuntimeError(f"no pricing known for {VISION_MODEL}; add it to MODEL_PRICES")
PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK = MODEL_PRICES[VISION_MODEL]


def get_client() -> OpenAI:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key)
