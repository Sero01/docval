"""Vision extraction for scanned PDFs via OpenRouter (Gemini 2.5 Flash)."""
from __future__ import annotations

import base64
import io
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import openai
import pypdfium2 as pdfium
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from docval.config import (PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK, VISION_MODEL,
                           get_client)
from docval.schema import StatementDoc, UsageStats

_FORMAT_RULES = (
    "Dates as YYYY-MM-DD. Many rows print only a day and month ('2 okt', "
    "'3 Jul') or a two-digit year ('03 avr. 25'); complete them from the "
    "statement period printed on the document — never guess a year. When a "
    "row has more than one date column, use the posting/booking date (the "
    "primary Date column), not the value, interest or effective date. "
    "Amounts as plain decimal strings without currency symbols or thousands "
    "separators. Each transaction has at most one of debit/credit set; rows "
    "printed without any amount (e.g. failed or informational lines) have "
    "both null. The description is the transaction's description/details "
    "text: when the table has a separate counterparty or payee column, take "
    "the description column, not the counterparty. Exclude anything that is "
    "not description text — no date fragments, and no account identifiers or "
    "reference numbers (IBAN, FPS/transaction ids) printed beneath the row. "
    "Where the details genuinely wrap onto several printed lines, join them "
    "with a single space."
)

PROMPT = (
    "Extract this bank statement completely and exactly. Return every transaction "
    "row. " + _FORMAT_RULES
)

PAGED_HEADER_PROMPT = (
    "This bank statement is processed page by page. You are given its FIRST "
    "page and, if the statement has more than one page, its LAST page. "
    "Extract the statement-level fields (bank name, account number, currency, "
    "period, opening balance; the closing balance is often printed near the "
    "end of the last page). Then return ONLY the transaction rows printed on "
    "the FIRST page image, completely and exactly, in print order. "
    + _FORMAT_RULES
)

PAGED_TXNS_PROMPT = (
    "This image is one page of a longer bank statement. Return every "
    "transaction row printed on THIS page, completely and exactly, in print "
    "order. Do not invent rows from other pages. " + _FORMAT_RULES
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


class _WirePageTxns(BaseModel):
    transactions: list[_WireTxn]


MAX_PAGE_PX = 2048  # image-PDF pages can be thousands of points tall; the
# model downscales internally anyway, so bigger renders only bloat the payload

MAX_OUTPUT_TOKENS = 32768  # a ~160-txn statement is ~10k tokens of JSON

_MAX_ATTEMPTS = 3


class TruncatedOutputError(Exception):
    """Model hit the output-token limit; the JSON is incomplete."""


def _rate_limited(e: Exception) -> bool:
    if isinstance(e, openai.RateLimitError):
        return True
    body = getattr(e, "body", None)
    return isinstance(body, dict) and body.get("code") == 429


def _retryable(e: Exception) -> bool:
    if isinstance(e, (ValidationError, TruncatedOutputError,
                      openai.RateLimitError, openai.APIConnectionError)):
        return True
    # a bare APIError is the mid-stream injected kind; typed status errors
    # (auth, bad request) are not worth retrying
    return type(e) is openai.APIError


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
_AMOUNT_JUNK = re.compile(r"(?i)\brs\.?\s*|\binr\b|[₹$€£\s]")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y",
                 "%d.%m.%Y", "%d %b %y", "%d.%m.%y", "%d/%m/%y")
_LONE_COMMA_DECIMAL = re.compile(r"^[^,]*,\d{2}$")


def _decimal_string(raw: str) -> str:
    """Normalize a printed amount to a plain decimal string.

    Locale is inferred per value rather than configured, because one
    benchmark run spans Dutch "1.925,00", Indian "7,79,226.50" and
    French-Canadian "10 662,91": whichever of "," and "." appears last is
    that value's decimal separator. A lone comma is decimal only when
    exactly two digits follow it ("19,25"), which is what separates it from
    US-style grouping ("1,000").
    """
    cleaned = _AMOUNT_JUNK.sub("", raw) or raw
    if "," in cleaned:
        decimal_is_comma = (cleaned.rfind(",") > cleaned.rfind(".")
                            if "." in cleaned
                            else bool(_LONE_COMMA_DECIMAL.match(cleaned)))
        if decimal_is_comma:
            return cleaned.replace(".", "").replace(",", ".")
        cleaned = cleaned.replace(",", "")
    if cleaned.count(".") > 1:
        # misread grouping separators ("6,056.445.83"): every dot but the
        # last is grouping; if the repair is numerically wrong, the
        # balance-chain validator flags it downstream
        whole, _, frac = cleaned.rpartition(".")
        cleaned = whole.replace(".", "") + "." + frac
    return cleaned


def _clean_amount(amount: str | None) -> str | None:
    if amount is None:
        return None
    cleaned = _decimal_string(amount)
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


_CURRENCY_SYMBOLS = {"$": "USD", "₹": "INR", "RS": "INR", "RS.": "INR",
                     "€": "EUR", "£": "GBP", "¥": "JPY"}


def _repair_year(iso: str, start: str, end: str) -> str:
    """Pull a transaction date into the statement period when the model
    invented its year.

    Rows printed without a year ("2 okt", "2 Jul") force the model to guess,
    and it guesses one unrelated to the statement. Only the year is
    corrected, and only when some year in the period makes the date fit: a
    wrong month is a genuine misread and stays visible to the validator.
    """
    try:
        txn = datetime.strptime(iso, "%Y-%m-%d").date()
        first = datetime.strptime(start, "%Y-%m-%d").date()
        last = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return iso
    if first <= txn <= last or first > last:
        return iso
    for year in range(first.year, last.year + 1):
        try:
            shifted = txn.replace(year=year)
        except ValueError:  # 29 Feb into a common year
            continue
        if first <= shifted <= last:
            return shifted.isoformat()
    return iso


def _normalize(wire: _WireStatement) -> dict:
    payload = wire.model_dump()
    printed = payload["currency"].strip()
    payload["currency"] = _CURRENCY_SYMBOLS.get(printed.upper(),
                                                printed.upper())
    for key in ("opening_balance", "closing_balance"):
        payload[key] = _decimal_string(payload[key]) or payload[key]
    for key in ("period_start", "period_end"):
        payload[key] = _clean_date(payload[key])
    for txn in payload["transactions"]:
        txn["original"] = {  # as-received values, before any cleaning
            "Date": txn["txn_date"], "Description": txn["description"],
            "Debit": txn["debit"] or "", "Credit": txn["credit"] or "",
            "Balance": txn["running_balance"] or ""}
        txn["txn_date"] = _repair_year(_clean_date(txn["txn_date"]),
                                       payload["period_start"],
                                       payload["period_end"])
        # detail blocks wrap across printed lines; the scored field is one string
        txn["description"] = " ".join(txn["description"].split())
        txn["debit"] = _clean_amount(txn["debit"])
        txn["credit"] = _clean_amount(txn["credit"])
        if txn["running_balance"] is not None:
            txn["running_balance"] = (_decimal_string(txn["running_balance"])
                                      or txn["running_balance"])
    return payload


def _image_part(jpeg: bytes) -> dict:
    b64 = base64.b64encode(jpeg).decode()
    return {"type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def _stream_json[W: BaseModel](client: OpenAI, model: str, content: list[dict],
                               schema: type[W], name: str,
                               tally: dict[str, int]) -> W:
    stream = client.chat.completions.create(
        model=model,
        temperature=0,  # extraction must be greedy, not sampled
        max_tokens=MAX_OUTPUT_TOKENS,
        # thinking tokens count against the output budget and truncate
        # long statements mid-JSON; extraction is transcription, not
        # reasoning
        extra_body={"reasoning": {"enabled": False}},
        # long generations exceed proxy timeouts unless streamed
        stream=True,
        stream_options={"include_usage": True},
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_schema", "json_schema": {
            "name": name, "strict": True,
            "schema": schema.model_json_schema()}})
    parts: list[str] = []
    finish_reason = None
    for chunk in stream:
        if chunk.usage is not None:
            tally["in"] += chunk.usage.prompt_tokens
            tally["out"] += chunk.usage.completion_tokens
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                parts.append(delta)
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
    if finish_reason == "length":
        raise TruncatedOutputError(
            f"output hit max_tokens={MAX_OUTPUT_TOKENS}; JSON incomplete")
    return schema.model_validate_json("".join(parts))


def _extract[W: BaseModel](client: OpenAI, model: str, content: list[dict],
                           schema: type[W], name: str,
                           tally: dict[str, int]) -> W:
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return _stream_json(client, model, content, schema, name, tally)
        except Exception as e:
            # truncation is deterministic at temperature 0: the identical
            # request truncates identically, so retrying only burns tokens —
            # the caller falls back to per-page extraction instead
            if isinstance(e, TruncatedOutputError):
                raise
            if attempt == _MAX_ATTEMPTS - 1 or not _retryable(e):
                raise
            if _rate_limited(e):
                # the provider aborts the stream mid-generation when the
                # per-minute token cap is hit; wait for the window to reset
                time.sleep(45 * (attempt + 1))
            elif isinstance(e, openai.APIError):
                # other provider aborts are bursty: instant retries land in
                # the same outage window (observed 3/3 back-to-back failures,
                # then success minutes later)
                time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def _parse_paged(client: OpenAI, model: str, pages: list[bytes],
                 tally: dict[str, int]) -> _WireStatement:
    header_content = [{"type": "text", "text": PAGED_HEADER_PROMPT},
                      _image_part(pages[0])]
    if len(pages) > 1:
        # the closing balance usually sits at the end of the last page
        header_content.append(_image_part(pages[-1]))
    head = _extract(client, model, header_content,
                    _WireStatement, "bank_statement", tally)
    txns = list(head.transactions)
    for page in pages[1:]:
        cont = _extract(client, model,
                        [{"type": "text", "text": PAGED_TXNS_PROMPT},
                         _image_part(page)],
                        _WirePageTxns, "statement_page", tally)
        txns.extend(cont.transactions)
    return head.model_copy(update={"transactions": txns})


def parse_vision(pdf_path: Path, client: OpenAI | None = None,
                 model: str = VISION_MODEL) -> tuple[StatementDoc, UsageStats]:
    client = client or get_client()
    pages = render_pages(pdf_path)
    content = [{"type": "text", "text": PROMPT},
               *(_image_part(p) for p in pages)]
    started = time.monotonic()
    tally = {"in": 0, "out": 0}  # every attempt is billed
    try:
        wire = _extract(client, model, content,
                        _WireStatement, "bank_statement", tally)
    except Exception as e:
        # dense statements overflow the output budget in one shot (10 of 13
        # held-out failures), come back as schema garbage, or get their long
        # stream aborted by the provider; per-page extraction keeps each
        # response small, rows are merged in print order, and the
        # balance-chain validator checks the merge
        if not (isinstance(e, (TruncatedOutputError, ValidationError))
                or type(e) is openai.APIError):  # typed status errors are fatal
            raise
        wire = _parse_paged(client, model, pages, tally)
    latency = time.monotonic() - started
    doc = StatementDoc.model_validate(_normalize(wire))  # never trust wire JSON
    usage = UsageStats(
        input_tokens=tally["in"],
        output_tokens=tally["out"],
        cost_usd=(tally["in"] * PRICE_IN_PER_MTOK
                  + tally["out"] * PRICE_OUT_PER_MTOK) / 1_000_000,
        latency_s=latency)
    return doc, usage
