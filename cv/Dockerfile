# Reproducible CV build image: WeasyPrint + Cyrillic-capable fonts.
# Used by `task build-cv` so the host needs nothing but Docker.
FROM python:3.12-slim

# WeasyPrint runtime libs + fonts that cover Latin and Cyrillic.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        fontconfig \
        fonts-noto-core \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        "weasyprint>=62,<64" \
        "jinja2>=3.1" \
        "pyyaml>=6" \
        "markdown>=3.6"

WORKDIR /work
ENTRYPOINT ["python", "build_cv.py"]
