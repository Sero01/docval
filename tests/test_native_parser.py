import random

import pytest

from datagen.generate import build_statement, render_pdf
from docval.parsers.native import UnsupportedLayoutError, parse_native


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_roundtrip_generated_statement(tmp_path, seed):
    gold = build_statement(random.Random(seed))
    pdf = tmp_path / "stmt.pdf"
    render_pdf(gold, pdf)
    parsed = parse_native(pdf)
    # original is extraction provenance, not statement content
    strip = {"transactions": {"__all__": {"original"}}}
    assert parsed.model_dump(exclude=strip) == gold.model_dump(exclude=strip)


def test_original_cells_preserved(tmp_path):
    # Benchmark scoring (Bankstatemently parsedScore) compares raw cell text
    # as printed in the PDF, keyed by the PDF's own column headers.
    gold = build_statement(random.Random(1))
    pdf = tmp_path / "stmt.pdf"
    render_pdf(gold, pdf)
    parsed = parse_native(pdf)
    first = parsed.transactions[0]
    assert first.original is not None
    assert set(first.original) == {"Date", "Description", "Debit", "Credit",
                                   "Balance"}
    assert first.original["Date"] == first.txn_date.isoformat()
    assert first.original["Description"] == first.description


def test_unknown_layout_raises(tmp_path):
    from weasyprint import HTML
    HTML(string="<h1>A totally different invoice</h1>").write_pdf(
        str(tmp_path / "other.pdf"))
    with pytest.raises(UnsupportedLayoutError):
        parse_native(tmp_path / "other.pdf")
