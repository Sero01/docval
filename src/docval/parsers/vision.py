"""Vision extraction for scanned PDFs via OpenRouter (Gemini 2.5 Flash)."""
from __future__ import annotations

import base64
import io
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pypdfium2 as pdfium
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from docval.config import (PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK, VISION_MODEL,
                           get_client)
from docval.schema import StatementDoc, UsageStats

PROMPT = (
    "Extract this bank statement completely and exactly. Return every transaction "
    "row. Dates as YYYY-MM-DD. Amounts as plain decimal strings without currency "
    "symbols or thousands separators. Each transaction has at most one of "
    "debit/credit set; rows printed without any amount (e.g. failed or "
    "informational lines) have both null. Copy descriptions verbatim."
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


MAX_PAGE_PX = 2048  # image-PDF pages can be thousands of points tall; the
# model downscales internally anyway, so bigger renders only bloat the payload

MAX_OUTPUT_TOKENS = 32768  # a ~160-txn statement is ~10k tokens of JSON


class TruncatedOutputError(Exception):
    """Model hit the output-token limit; the JSON is incomplete."""


def render_pages(pdf_path: Path, dpi: int = 200) -> list[bytes]:
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        pages = []
        for page in doc:
            w_pt, h_pt = page.get_size()
            scale = min(dpi / 72, MAX_PAGE_PX / max(w_pt, h_pt))
            img = page.render(scale=scale).to_pil()
            buf = io.BytesIO()
            # JPEG: 200-dpi PNGs of multi-page scans exceed provider request
            # size limits (HTTP 413 observed on 6-page documents)
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            pages.append(buf.getvalue())
        return pages
    finally:
        doc.close()


# Models copy printed formats faithfully regardless of prompt instructions;
# normalization to canonical values is deterministic code, not model behavior.
_AMOUNT_JUNK = re.compile(r"(?i)\brs\.?\s*|\binr\b|[₹$€£,\s]")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y")


def _clean_amount(amount: str | None) -> str | None:
    if amount is None:
        return None
    cleaned = _AMOUNT_JUNK.sub("", amount) or amount
    try:
        # "0.00" for an empty cell means no debit/credit at all
        return None if Decimal(cleaned) == 0 else cleaned
    except InvalidOperation:
        return amount  # let StatementDoc validation report the garbage


def _clean_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw  # let StatementDoc validation report the garbage


def _normalize(wire: _WireStatement) -> dict:
    payload = wire.model_dump()
    for key in ("opening_balance", "closing_balance"):
        payload[key] = _AMOUNT_JUNK.sub("", payload[key]) or payload[key]
    for key in ("period_start", "period_end"):
        payload[key] = _clean_date(payload[key])
    for txn in payload["transactions"]:
        txn["txn_date"] = _clean_date(txn["txn_date"])
        txn["debit"] = _clean_amount(txn["debit"])
        txn["credit"] = _clean_amount(txn["credit"])
        if txn["running_balance"] is not None:
            txn["running_balance"] = (_AMOUNT_JUNK.sub("", txn["running_balance"])
                                      or txn["running_balance"])
    return payload


def parse_vision(pdf_path: Path, client: OpenAI | None = None,
                 model: str = VISION_MODEL) -> tuple[StatementDoc, UsageStats]:
    client = client or get_client()
    content: list[dict] = [{"type": "text", "text": PROMPT}]
    for jpeg in render_pages(pdf_path):
        b64 = base64.b64encode(jpeg).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    started = time.monotonic()
    wire: _WireStatement | None = None
    tokens_in = tokens_out = 0  # every attempt is billed
    for attempt in (0, 1):  # providers occasionally drop a response mid-stream
        resp = client.chat.completions.create(
            model=model,
            temperature=0,  # extraction must be greedy, not sampled
            max_tokens=MAX_OUTPUT_TOKENS,
            # thinking tokens count against the output budget and truncate long
            # statements mid-JSON; extraction needs transcription, not reasoning
            extra_body={"reasoning": {"enabled": False}},
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "bank_statement", "strict": True,
                "schema": _WireStatement.model_json_schema()}})
        tokens_in += resp.usage.prompt_tokens
        tokens_out += resp.usage.completion_tokens
        try:
            if resp.choices[0].finish_reason == "length":
                raise TruncatedOutputError(
                    f"output hit max_tokens={MAX_OUTPUT_TOKENS}; JSON incomplete")
            wire = _WireStatement.model_validate_json(resp.choices[0].message.content)
            break
        except (ValidationError, TruncatedOutputError):
            if attempt == 1:
                raise
    latency = time.monotonic() - started
    doc = StatementDoc.model_validate(_normalize(wire))  # never trust wire JSON
    usage = UsageStats(
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        cost_usd=(tokens_in * PRICE_IN_PER_MTOK
                  + tokens_out * PRICE_OUT_PER_MTOK) / 1_000_000,
        latency_s=latency)
    return doc, usage
