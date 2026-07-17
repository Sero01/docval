"""Gradio demo: bundled samples (free) + rate-limited live upload."""
from __future__ import annotations

from pathlib import Path

import gradio as gr

from docval.pipeline import ExtractionResult, extract

MAX_PAGES = 5
MAX_BYTES = 10 * 1024 * 1024
SAMPLES = sorted(Path("samples").glob("*.pdf"))

BADGE = {"pass": "✅", "warn": "⚠️", "fail": "❌"}


def public_error(error: str | None) -> str:
    # The catch-all pipeline error embeds exception type + message for the
    # eval harness; don't leak that to anonymous visitors.
    if error is None or error.startswith("extraction failed:"):
        return "extraction failed — the document could not be processed"
    return error


def render(result: ExtractionResult):
    if result.doc is None:
        return [], f"❌ {public_error(result.error)}", "route: error"
    rows = [[t.txn_date.isoformat(), t.description,
             str(t.debit or ""), str(t.credit or ""), str(t.running_balance or "")]
            for t in result.doc.transactions]
    findings = "\n".join(
        f"{BADGE[f.severity.value]} **{f.check}** — {f.message}"
        for f in result.report.findings)
    meta = f"route: {result.route}"
    if result.usage:
        meta += (f" · cost ${result.usage.cost_usd:.4f}"
                 f" · {result.usage.latency_s:.1f}s")
    return rows, findings, meta


def show_sample(name: str):
    result_file = Path("samples") / (Path(name).stem + ".result.json")
    return render(ExtractionResult.model_validate_json(result_file.read_text()))


def run_upload(file):
    if file is None:
        return [], "Upload a PDF first.", ""
    path = Path(file)
    if path.stat().st_size > MAX_BYTES:
        return [], "❌ File too large (max 10 MB).", ""
    with path.open("rb") as f:
        if f.read(5) != b"%PDF-":
            return [], "❌ Not a PDF file.", ""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(path))
    n_pages = len(doc)
    doc.close()
    if n_pages > MAX_PAGES:
        return [], f"❌ Too many pages (max {MAX_PAGES}).", ""
    return render(extract(path))


HEADERS = ["Date", "Description", "Debit", "Credit", "Balance"]

with gr.Blocks(title="DocVal — bank-statement extraction + validation") as demo:
    gr.Markdown("# DocVal\nExtracts bank statements to structured JSON, then "
                "validates them (balance continuity, date sanity).")
    with gr.Tab("Samples (precomputed)"):
        pick = gr.Dropdown([p.name for p in SAMPLES], label="Sample statement")
        table_s = gr.Dataframe(headers=HEADERS)
        findings_s, meta_s = gr.Markdown(), gr.Markdown()
        pick.change(show_sample, pick, [table_s, findings_s, meta_s])
    with gr.Tab("Try your own (live)"):
        up = gr.File(file_types=[".pdf"], label="PDF, max 5 pages / 10 MB")
        btn = gr.Button("Extract & validate")
        table_u = gr.Dataframe(headers=HEADERS)
        findings_u, meta_u = gr.Markdown(), gr.Markdown()
        btn.click(run_upload, up, [table_u, findings_u, meta_u],
                  concurrency_limit=2)

demo.queue(max_size=10)
if __name__ == "__main__":
    demo.launch()
