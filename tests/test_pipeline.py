import random

from datagen.generate import build_statement, render_pdf
from docval.pipeline import extract
from docval.validate import Severity


def test_native_pdf_takes_native_route(tmp_path):
    render_pdf(build_statement(random.Random(5)), tmp_path / "n.pdf")
    result = extract(tmp_path / "n.pdf", allow_vision=False)
    assert result.route == "native"
    assert result.report.overall == Severity.PASS
    assert result.error is None


def test_vision_disabled_scanned_pdf_yields_error(tmp_path):
    from datagen.scanify import make_scan_variant
    render_pdf(build_statement(random.Random(5)), tmp_path / "n.pdf")
    make_scan_variant(tmp_path / "n.pdf", tmp_path / "s.pdf")
    result = extract(tmp_path / "s.pdf", allow_vision=False)
    assert result.route == "error"
    assert result.doc is None
    assert "vision" in result.error


def test_extraction_error_keeps_diagnostic_detail(tmp_path, monkeypatch):
    import docval.pipeline as pipeline
    from datagen.scanify import make_scan_variant

    def boom(*a, **kw):
        raise ValueError("model returned currency 'Indian Rupee'")

    monkeypatch.setattr(pipeline, "parse_vision", boom)
    render_pdf(build_statement(random.Random(5)), tmp_path / "n.pdf")
    make_scan_variant(tmp_path / "n.pdf", tmp_path / "s.pdf")
    result = extract(tmp_path / "s.pdf")
    assert result.route == "error"
    assert "ValueError" in result.error
    assert "Indian Rupee" in result.error  # detail must survive, not just the type
