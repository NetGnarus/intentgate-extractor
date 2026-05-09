"""FastAPI entrypoint for the intent extractor service.

The service exposes two endpoints:

  GET  /healthz         — liveness probe, reports current mode and model
  POST /v1/extract      — turn a user prompt into structured intent

Run locally:

    uvicorn app.main:app --reload --port 8090

Or via Docker:

    docker build -t intentgate/extractor:dev .
    docker run --rm -p 8090:8090 -e EXTRACTOR_STUB=true intentgate/extractor:dev
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException

from .extractor import build_extractor
from .models import ExtractRequest, ExtractResponse, HealthResponse

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("extractor")

app = FastAPI(
    title="IntentGate Extractor",
    version="0.1.0",
    description=(
        "Turns free-form user prompts into structured intent for the "
        "IntentGate gateway's second-of-four checks."
    ),
)

# Built once at startup; the choice (stub vs anthropic) is driven by
# environment variables. See extractor.build_extractor for the rules.
_extractor = build_extractor()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", mode=_extractor.name, model=_extractor.model)


@app.post("/v1/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest) -> ExtractResponse:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is empty")
    try:
        intent, latency_ms = _extractor.extract(req.prompt)
    except Exception as e:  # pragma: no cover — depends on Anthropic SDK
        logger.exception("extraction failed")
        raise HTTPException(status_code=500, detail=f"extraction failed: {e!s}") from e

    logger.info(
        "extracted prompt (agent=%s, tools_allow=%d, tools_deny=%d, conf=%.2f, latency=%dms)",
        req.agent_id or "-",
        len(intent.allowed_tools),
        len(intent.forbidden_tools),
        intent.confidence,
        latency_ms,
    )
    return ExtractResponse(
        intent=intent,
        model=_extractor.model,
        latency_ms=latency_ms,
    )
