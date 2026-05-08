# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so they cache independently of source.
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install \
      "fastapi>=0.110,<0.116" \
      "uvicorn[standard]>=0.27,<0.32" \
      "pydantic>=2.5,<3" \
      "anthropic>=0.34,<1"

COPY app ./app

# Run as non-root.
RUN useradd --system --uid 1000 extractor && \
    chown -R extractor:extractor /app
USER extractor

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
