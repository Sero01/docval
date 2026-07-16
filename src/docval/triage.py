"""Route PDFs: usable text layer -> native parser, otherwise vision."""
from __future__ import annotations

from pathlib import Path

import pdfplumber


def is_native(pdf_path: Path, min_chars: int = 100) -> bool:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "".join((page.extract_text() or "") for page in pdf.pages[:2])
        return len(text.strip()) >= min_chars
    except Exception:
        return False
