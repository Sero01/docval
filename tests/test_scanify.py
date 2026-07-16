import random

import pdfplumber

from datagen.generate import build_statement, render_pdf
from datagen.scanify import make_scan_variant


def test_lower_jpeg_quality_shrinks_output(tmp_path):
    doc = build_statement(random.Random(7))
    src = tmp_path / "native.pdf"
    render_pdf(doc, src)
    lo, hi = tmp_path / "lo.pdf", tmp_path / "hi.pdf"
    make_scan_variant(src, lo, jpeg_quality=30)
    make_scan_variant(src, hi, jpeg_quality=95)
    assert lo.stat().st_size < hi.stat().st_size
    with pdfplumber.open(lo) as pdf:
        assert len((pdf.pages[0].extract_text() or "").strip()) == 0


def test_scan_variant_has_no_text_layer(tmp_path):
    doc = build_statement(random.Random(7))
    src = tmp_path / "native.pdf"
    render_pdf(doc, src)
    out = tmp_path / "scan.pdf"
    make_scan_variant(src, out)
    with pdfplumber.open(out) as pdf:
        text = pdf.pages[0].extract_text() or ""
    assert len(text.strip()) == 0
    assert out.stat().st_size > 10_000
