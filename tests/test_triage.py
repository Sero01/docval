import random

from datagen.generate import build_statement, render_pdf
from datagen.scanify import make_scan_variant
from docval.triage import is_native


def test_native_pdf_detected(tmp_path):
    render_pdf(build_statement(random.Random(1)), tmp_path / "n.pdf")
    assert is_native(tmp_path / "n.pdf") is True


def test_scanned_pdf_detected(tmp_path):
    render_pdf(build_statement(random.Random(1)), tmp_path / "n.pdf")
    make_scan_variant(tmp_path / "n.pdf", tmp_path / "s.pdf")
    assert is_native(tmp_path / "s.pdf") is False


def test_garbage_file_routes_to_vision(tmp_path):
    (tmp_path / "junk.pdf").write_bytes(b"not a pdf at all")
    assert is_native(tmp_path / "junk.pdf") is False
