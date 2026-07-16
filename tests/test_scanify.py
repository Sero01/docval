import random

import pdfplumber

from datagen.generate import build_statement, render_pdf
from datagen.scanify import make_scan_variant


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
