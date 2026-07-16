"""Single entry point: triage -> parse -> validate. Never raises."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import openai
from pydantic import BaseModel

from docval.parsers.native import UnsupportedLayoutError, parse_native
from docval.parsers.vision import parse_vision
from docval.schema import StatementDoc, UsageStats
from docval.triage import is_native
from docval.validate import ValidationReport, validate_statement


class ExtractionResult(BaseModel):
    source: str
    route: Literal["native", "vision", "error"]
    doc: StatementDoc | None = None
    report: ValidationReport | None = None
    usage: UsageStats | None = None
    error: str | None = None


def extract(pdf_path: Path, client=None,
            allow_vision: bool = True) -> ExtractionResult:
    source = str(pdf_path)
    doc: StatementDoc | None = None
    usage: UsageStats | None = None
    route: Literal["native", "vision", "error"] = "error"

    if is_native(pdf_path):
        try:
            doc, route = parse_native(pdf_path), "native"
        except UnsupportedLayoutError:
            pass  # fall through to vision

    if doc is None:
        if not allow_vision:
            return ExtractionResult(source=source, route="error",
                                    error="scanned/unknown layout and vision path disabled")
        try:
            (doc, usage), route = parse_vision(pdf_path, client=client), "vision"
        except openai.RateLimitError:
            return ExtractionResult(source=source, route="error",
                                    error="rate limited by model provider; retry later")
        except openai.APIStatusError as e:
            return ExtractionResult(source=source, route="error",
                                    error=f"model API error (status {e.status_code})")
        except Exception as e:
            detail = str(e).replace("\n", " ")[:300]
            return ExtractionResult(source=source, route="error",
                                    error=f"extraction failed: {type(e).__name__}: {detail}")

    return ExtractionResult(source=source, route=route, doc=doc, usage=usage,
                            report=validate_statement(doc))
