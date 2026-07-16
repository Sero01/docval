import json
import random
from types import SimpleNamespace

from datagen.generate import build_statement, render_pdf
from datagen.scanify import make_scan_variant
from docval.parsers.vision import parse_vision, render_pages


class StubClient:
    """Mimics a streaming openai chat.completions.create."""

    def __init__(self, payload: dict, finish_reason: str = "stop"):
        self._payload = payload
        self._finish_reason = finish_reason
        self.last_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _content(self) -> str:
        return json.dumps(self._payload)

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        text = self._content()
        mid = len(text) // 2

        def chunks():
            for piece in (text[:mid], text[mid:]):
                yield SimpleNamespace(usage=None, choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=piece), finish_reason=None)])
            yield SimpleNamespace(usage=None, choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None),
                finish_reason=self._finish_reason)])
            yield SimpleNamespace(choices=[], usage=SimpleNamespace(
                prompt_tokens=1000, completion_tokens=500))

        return chunks()


PAYLOAD = {
    "bank_name": "Meridian Bank", "account_number": "123456789012",
    "currency": "INR", "period_start": "2026-01-01", "period_end": "2026-01-31",
    "opening_balance": "1000.00", "closing_balance": "900.00",
    "transactions": [{"txn_date": "2026-01-05", "description": "ATM WDL",
                      "debit": "100.00", "credit": None, "running_balance": "900.00"}],
}


def _scan_pdf(tmp_path):
    native = tmp_path / "n.pdf"
    render_pdf(build_statement(random.Random(3)), native)
    scan = tmp_path / "s.pdf"
    make_scan_variant(native, scan)
    return scan


def test_render_pages_returns_jpeg_bytes(tmp_path):
    # JPEG, not PNG: multi-page 200-dpi PNG scans exceed the provider's
    # request size limit (observed HTTP 413 on 6-page AgamiAI documents)
    pages = render_pages(_scan_pdf(tmp_path))
    assert len(pages) >= 1
    assert pages[0][:3] == b"\xff\xd8\xff"


def test_render_pages_caps_pixel_size_of_huge_pages(tmp_path):
    # Image-PDFs often map 1 px to 1 pt, so a 300-dpi scan page is ~3500 pt
    # and naive dpi scaling produces ~67 MP images (observed HTTP 413).
    import io

    from PIL import Image

    big = tmp_path / "big.pdf"
    Image.new("L", (3500, 5000), 255).save(big, format="PDF")
    pages = render_pages(big)
    img = Image.open(io.BytesIO(pages[0]))
    assert max(img.size) <= 2048


def test_parse_vision_builds_statement_and_usage(tmp_path):
    stub = StubClient(PAYLOAD)
    doc, usage = parse_vision(_scan_pdf(tmp_path), client=stub)
    assert doc.bank_name == "Meridian Bank"
    assert str(doc.opening_balance) == "1000.00"
    assert usage.input_tokens == 1000 and usage.output_tokens == 500
    assert usage.cost_usd > 0
    assert stub.last_kwargs["model"] == "google/gemini-2.5-flash-lite"
    assert stub.last_kwargs["response_format"]["type"] == "json_schema"
    assert stub.last_kwargs["temperature"] == 0  # extraction must be greedy
    # thinking eats the output budget and truncates long statements mid-JSON
    assert stub.last_kwargs["max_tokens"] >= 32768
    assert stub.last_kwargs["extra_body"]["reasoning"]["enabled"] is False
    # non-streaming responses over ~100s get cut by intermediary proxies
    assert stub.last_kwargs["stream"] is True


def test_truncated_output_raises_named_error(tmp_path):
    import pytest

    from docval.parsers.vision import TruncatedOutputError

    stub = StubClient(PAYLOAD, finish_reason="length")
    with pytest.raises(TruncatedOutputError):
        parse_vision(_scan_pdf(tmp_path), client=stub)


def test_printed_formats_normalized(tmp_path):
    # Models copy what is printed: comma-grouped amounts, currency junk,
    # and human date formats. Normalization must be deterministic code.
    payload = {
        "bank_name": "Royal Commercial Bank", "account_number": "42146130224",
        "currency": "INR", "period_start": "01 Jan 2024",
        "period_end": "31/03/2024",
        "opening_balance": "7,79,226.50", "closing_balance": "Rs. 2,482,196.19",
        "transactions": [{"txn_date": "02-01-2024", "description": "NEFT",
                          "debit": None, "credit": "₹1,544.32",
                          "running_balance": "7,80,770.82"}],
    }
    from datetime import date
    from decimal import Decimal

    doc, _ = parse_vision(_scan_pdf(tmp_path), client=StubClient(payload))
    # raw printed values survive normalization as extraction provenance
    assert doc.transactions[0].original == {
        "Date": "02-01-2024", "Description": "NEFT", "Debit": "",
        "Credit": "₹1,544.32", "Balance": "7,80,770.82"}
    assert doc.period_start == date(2024, 1, 1)
    assert doc.period_end == date(2024, 3, 31)
    assert doc.opening_balance == Decimal("779226.50")
    assert doc.closing_balance == Decimal("2482196.19")
    assert doc.transactions[0].credit == Decimal("1544.32")
    assert doc.transactions[0].txn_date == date(2024, 1, 2)


def test_misread_separator_amounts_repaired(tmp_path):
    # Noisy scans make models misread grouping separators ("60,56,445.83"
    # transcribed as "6,056.445.83"). All dots but the last are grouping.
    from decimal import Decimal

    payload = dict(PAYLOAD, transactions=[
        {"txn_date": "2026-01-05", "description": "NEFT",
         "debit": None, "credit": "6,056.445.83", "running_balance": None}])
    doc, _ = parse_vision(_scan_pdf(tmp_path), client=StubClient(payload))
    assert doc.transactions[0].credit == Decimal("6056445.83")


def test_flaky_invalid_json_retried_once(tmp_path):
    class FlakyStub(StubClient):
        def __init__(self, payload):
            super().__init__(payload)
            self.calls = 0

        def _content(self) -> str:
            self.calls += 1
            if self.calls == 1:  # provider drops the stream mid-generation
                return '{\n  "bank_name": "Roy'
            return super()._content()

    stub = FlakyStub(PAYLOAD)
    doc, usage = parse_vision(_scan_pdf(tmp_path), client=stub)
    assert stub.calls == 2
    assert doc.bank_name == "Meridian Bank"
    assert usage.input_tokens == 2000  # both attempts were billed


def test_midstream_rate_limit_retried_with_backoff(tmp_path, monkeypatch):
    # OpenRouter aborts long generations mid-stream with a 429 error event
    # when the per-minute token cap is hit; back off and retry.
    import time as time_mod

    import httpx
    import openai

    sleeps: list[float] = []
    monkeypatch.setattr(time_mod, "sleep", lambda s: sleeps.append(s))

    class RateLimitedStub(StubClient):
        def __init__(self, payload):
            super().__init__(payload)
            self.calls = 0

        def _create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise openai.APIError(
                    "JSON error injected into SSE stream",
                    httpx.Request("POST", "https://openrouter.ai"),
                    body={"code": 429,
                          "metadata": {"error_type": "rate_limit_exceeded"}})
            return super()._create(**kwargs)

    stub = RateLimitedStub(PAYLOAD)
    doc, _ = parse_vision(_scan_pdf(tmp_path), client=stub)
    assert stub.calls == 2
    assert doc.bank_name == "Meridian Bank"
    assert sleeps and sleeps[0] >= 30  # rate limits need a real pause


def test_midstream_provider_error_retried_with_short_backoff(tmp_path, monkeypatch):
    # Provider hiccups abort the stream with a bare (non-429) APIError and
    # are bursty: three instant retries all land in the same outage window
    # (observed live — 3/3 back-to-back failures, then success minutes
    # later). A short pause between attempts must separate them.
    import time as time_mod

    import httpx
    import openai

    sleeps: list[float] = []
    monkeypatch.setattr(time_mod, "sleep", lambda s: sleeps.append(s))

    class MidstreamErrorStub(StubClient):
        def __init__(self, payload):
            super().__init__(payload)
            self.calls = 0

        def _create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise openai.APIError(
                    "JSON error injected into SSE stream",
                    httpx.Request("POST", "https://openrouter.ai"),
                    body=None)
            return super()._create(**kwargs)

    stub = MidstreamErrorStub(PAYLOAD)
    doc, _ = parse_vision(_scan_pdf(tmp_path), client=stub)
    assert stub.calls == 2
    assert doc.bank_name == "Meridian Bank"
    assert sleeps and 0 < sleeps[0] < 30  # pause, but far less than a 429


def test_zero_amounts_coerced_to_none(tmp_path):
    # Models sometimes emit "0.00" for the empty amount column instead of
    # null; a zero debit/credit is no debit/credit.
    payload = dict(PAYLOAD, transactions=[
        {"txn_date": "2026-01-05", "description": "ATM WDL",
         "debit": "0.00", "credit": "500.00", "running_balance": "1500.00"},
        {"txn_date": "2026-01-06", "description": "FAILED-INSUFFICIENT FUNDS",
         "debit": "0.00", "credit": "0.00", "running_balance": "1500.00"},
    ])
    doc, _ = parse_vision(_scan_pdf(tmp_path), client=StubClient(payload))
    assert doc.transactions[0].debit is None
    assert str(doc.transactions[0].credit) == "500.00"
    assert doc.transactions[1].debit is None and doc.transactions[1].credit is None
