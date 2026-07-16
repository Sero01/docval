import random

from docval.validate import Severity, validate_statement
from datagen.generate import build_statement, render_pdf


def test_generated_statement_is_internally_consistent():
    doc = build_statement(random.Random(42))
    assert len(doc.transactions) >= 8
    assert validate_statement(doc).overall == Severity.PASS


def test_render_pdf_writes_file(tmp_path):
    doc = build_statement(random.Random(42))
    out = tmp_path / "stmt.pdf"
    render_pdf(doc, out)
    assert out.stat().st_size > 1000
