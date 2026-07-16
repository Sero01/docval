import json
import random
from types import SimpleNamespace

from datagen.generate import build_statement, render_pdf
from datagen.scanify import make_scan_variant
from docval.parsers.vision import parse_vision, render_pages


class StubClient:
    """Mimics openai chat.completions.create, returns a canned statement."""

    def __init__(self, payload: dict):
        self._payload = payload
        self.last_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(self._payload)))],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500))


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


def test_render_pages_returns_png_bytes(tmp_path):
    pages = render_pages(_scan_pdf(tmp_path))
    assert len(pages) >= 1
    assert pages[0][:8] == b"\x89PNG\r\n\x1a\n"


def test_parse_vision_builds_statement_and_usage(tmp_path):
    stub = StubClient(PAYLOAD)
    doc, usage = parse_vision(_scan_pdf(tmp_path), client=stub)
    assert doc.bank_name == "Meridian Bank"
    assert str(doc.opening_balance) == "1000.00"
    assert usage.input_tokens == 1000 and usage.output_tokens == 500
    assert usage.cost_usd > 0
    assert stub.last_kwargs["model"] == "google/gemini-2.5-flash"
    assert stub.last_kwargs["response_format"]["type"] == "json_schema"
