"""Vision extraction for scanned PDFs via OpenRouter (Gemini 2.5 Flash)."""
from __future__ import annotations

import base64
import io
import time
from pathlib import Path

import pypdfium2 as pdfium
from openai import OpenAI
from pydantic import BaseModel

from docval.config import (PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK, VISION_MODEL,
                           get_client)
from docval.schema import StatementDoc, UsageStats

PROMPT = (
    "Extract this bank statement completely and exactly. Return every transaction "
    "row. Dates as YYYY-MM-DD. Amounts as plain decimal strings without currency "
    "symbols or thousands separators. Each transaction has exactly one of "
    "debit/credit set; the other must be null. Copy descriptions verbatim."
)


class _WireTxn(BaseModel):
    txn_date: str
    description: str
    debit: str | None
    credit: str | None
    running_balance: str | None


class _WireStatement(BaseModel):
    bank_name: str
    account_number: str
    currency: str
    period_start: str
    period_end: str
    opening_balance: str
    closing_balance: str
    transactions: list[_WireTxn]


def render_pages(pdf_path: Path, dpi: int = 200) -> list[bytes]:
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        pages = []
        for page in doc:
            img = page.render(scale=dpi / 72).to_pil()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            pages.append(buf.getvalue())
        return pages
    finally:
        doc.close()


def parse_vision(pdf_path: Path, client: OpenAI | None = None,
                 model: str = VISION_MODEL) -> tuple[StatementDoc, UsageStats]:
    client = client or get_client()
    content: list[dict] = [{"type": "text", "text": PROMPT}]
    for png in render_pages(pdf_path):
        b64 = base64.b64encode(png).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}})
    started = time.monotonic()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_schema", "json_schema": {
            "name": "bank_statement", "strict": True,
            "schema": _WireStatement.model_json_schema()}})
    latency = time.monotonic() - started
    wire = _WireStatement.model_validate_json(resp.choices[0].message.content)
    doc = StatementDoc.model_validate(wire.model_dump())  # re-validation: never trust wire JSON
    usage = UsageStats(
        input_tokens=resp.usage.prompt_tokens,
        output_tokens=resp.usage.completion_tokens,
        cost_usd=(resp.usage.prompt_tokens * PRICE_IN_PER_MTOK
                  + resp.usage.completion_tokens * PRICE_OUT_PER_MTOK) / 1_000_000,
        latency_s=latency)
    return doc, usage
