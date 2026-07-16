import random
from decimal import Decimal

import pdfplumber
import pytest

from docval.validate import Severity, validate_statement
from datagen.generate import build_statement, money_inr, render_pdf


def test_generated_statement_is_internally_consistent():
    doc = build_statement(random.Random(42))
    assert len(doc.transactions) >= 8
    assert validate_statement(doc).overall == Severity.PASS


def test_render_pdf_writes_file(tmp_path):
    doc = build_statement(random.Random(42))
    out = tmp_path / "stmt.pdf"
    render_pdf(doc, out)
    assert out.stat().st_size > 1000


def test_money_inr_uses_lakh_grouping():
    assert money_inr(Decimal("123456.78")) == "1,23,456.78"
    assert money_inr(Decimal("12345678.90")) == "1,23,45,678.90"
    assert money_inr(Decimal("999.50")) == "999.50"
    assert money_inr(Decimal("1000.00")) == "1,000.00"
    assert money_inr(None) == ""


def test_multipage_statement_roundtrips_natively(tmp_path):
    gold = build_statement(random.Random(9), min_txns=90, max_txns=110)
    pdf = tmp_path / "big.pdf"
    render_pdf(gold, pdf)
    with pdfplumber.open(pdf) as p:
        assert len(p.pages) >= 2
    from docval.parsers.native import parse_native
    strip = {"transactions": {"__all__": {"original"}}}
    assert parse_native(pdf).model_dump(exclude=strip) == gold.model_dump(exclude=strip)


def test_descriptions_are_varied():
    doc = build_statement(random.Random(11), min_txns=90, max_txns=110)
    assert len({t.description for t in doc.transactions}) > 10


def test_template_b_routes_to_vision(tmp_path):
    from docval.parsers.native import UnsupportedLayoutError, parse_native
    from docval.triage import is_native

    doc = build_statement(random.Random(13))
    pdf = tmp_path / "b.pdf"
    render_pdf(doc, pdf, template="bank_b.html")
    assert is_native(pdf) is True  # has a text layer...
    with pytest.raises(UnsupportedLayoutError):  # ...but layout is foreign
        parse_native(pdf)
