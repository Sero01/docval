"""Demo-boundary hardening: error sanitization and upload validation."""
from pathlib import Path

from app import public_error, render, run_upload
from docval.pipeline import ExtractionResult


def test_catchall_error_is_not_leaked():
    result = ExtractionResult(
        source="x.pdf", route="error",
        error="extraction failed: RuntimeError: OPENROUTER_API_KEY is not set")
    _, findings, _ = render(result)
    assert "OPENROUTER" not in findings
    assert "RuntimeError" not in findings
    assert "extraction failed" in findings


def test_curated_errors_pass_through():
    msg = "rate limited by model provider; retry later"
    assert public_error(msg) == msg


def test_upload_rejects_non_pdf(tmp_path: Path):
    fake = tmp_path / "not_a_pdf.pdf"
    fake.write_bytes(b"hello, definitely not a pdf")
    _, findings, _ = run_upload(str(fake))
    assert "Not a PDF" in findings
