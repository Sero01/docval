"""Turn a native PDF into a noisy image-only 'scanned' PDF."""
from __future__ import annotations

import io
import random
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter


def _jpeg_roundtrip(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def make_scan_variant(src_pdf: Path, out_pdf: Path, dpi: int = 150,
                      jpeg_quality: int = 80) -> None:
    rng = random.Random(str(src_pdf))
    pages: list[Image.Image] = []
    doc = pdfium.PdfDocument(str(src_pdf))
    try:
        for page in doc:
            img = page.render(scale=dpi / 72).to_pil().convert("L")
            img = img.rotate(rng.uniform(-1.5, 1.5), expand=True, fillcolor=255)
            img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.7)))
            arr = np.asarray(img, dtype=np.int16)
            noise = np.random.default_rng(rng.randrange(2**32)).normal(0, 8, arr.shape)
            arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
            pages.append(_jpeg_roundtrip(Image.fromarray(arr).convert("RGB"),
                                         jpeg_quality))
    finally:
        doc.close()
    pages[0].save(out_pdf, save_all=True, append_images=pages[1:],
                  resolution=float(dpi), quality=jpeg_quality)
