FROM python:3.12-slim

# weasyprint needs pango/gdk-pixbuf at runtime (same list as packages.txt)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

USER appuser

ENV GRADIO_SERVER_NAME=0.0.0.0
# Render provides PORT; default to gradio's 7860 for local runs
CMD ["sh", "-c", "GRADIO_SERVER_PORT=${PORT:-7860} python app.py"]
