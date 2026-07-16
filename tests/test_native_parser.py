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
    assert parsed == gold


def test_unknown_layout_raises(tmp_path):
    from weasyprint import HTML
    HTML(string="<h1>A totally different invoice</h1>").write_pdf(
        str(tmp_path / "other.pdf"))
    with pytest.raises(UnsupportedLayoutError):
        parse_native(tmp_path / "other.pdf")
