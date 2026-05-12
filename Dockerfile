# syntax=docker/dockerfile:1.7

# Pinned to match requires-python in pyproject.toml. Bump both together.
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy project metadata + source, then install. We install the package
# itself (which pulls deps from pyproject.toml) so deps stay in one
# place. Slight cache-locality cost vs. inlining deps in this Dockerfile;
# eliminates dep-drift in exchange.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# Run as non-root.
RUN useradd --system --uid 1000 extractor && \
    chown -R extractor:extractor /app
USER extractor

# OCI labels — surfaced on the GHCR package page and by `docker inspect`.
LABEL org.opencontainers.image.title="intentgate-extractor"
LABEL org.opencontainers.image.description="Intent extractor service for IntentGate (FastAPI + Claude Haiku, with offline stub mode)"
LABEL org.opencontainers.image.source="https://github.com/NetGnarus/intentgate-extractor"
LABEL org.opencontainers.image.url="https://github.com/NetGnarus/intentgate-extractor"
LABEL org.opencontainers.image.documentation="https://github.com/NetGnarus/intentgate-extractor#readme"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.vendor="NetGnarus"

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
