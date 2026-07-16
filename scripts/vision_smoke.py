"""Live end-to-end check of the vision path against one generated scan."""
from pathlib import Path

from docval.parsers.vision import parse_vision
from docval.validate import validate_statement

doc, usage = parse_vision(Path("data/generated/stmt_0000_scan.pdf"))
print(doc.model_dump_json(indent=2))
print("validation:", validate_statement(doc).overall.value)
print(f"cost=${usage.cost_usd:.4f} latency={usage.latency_s:.1f}s "
      f"tokens={usage.input_tokens}/{usage.output_tokens}")
