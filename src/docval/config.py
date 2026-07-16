"""Runtime configuration. Model choice is config, never hardcoded in parsers."""
from __future__ import annotations

import os

from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
VISION_MODEL = "google/gemini-2.5-flash"
PRICE_IN_PER_MTOK = 0.30
PRICE_OUT_PER_MTOK = 2.50


def get_client() -> OpenAI:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key)
