"""End-to-end tests against the FastAPI app via httpx + ASGI transport.

These tests DON'T spin up a real network server; httpx talks to the
FastAPI ASGI app in-process. They exercise request validation, the
healthz contract, and that /v1/extract returns the stub result when
EXTRACTOR_STUB=true is set in the environment at import time.

We force stub mode at the top of the module so these tests never
require an Anthropic API key.
"""

from __future__ import annotations

import os

os.environ["EXTRACTOR_STUB"] = "true"

# Import AFTER setting the env var so build_extractor() picks stub mode.
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_healthz_reports_stub_mode() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "stub"


def test_extract_returns_intent_for_invoice_prompt() -> None:
    r = client.post(
        "/v1/extract",
        json={"prompt": "Process today's AP invoices", "agent_id": "finance-copilot-v3"},
    )
    assert r.status_code == 200
    body = r.json()
    intent = body["intent"]
    assert "read_invoice" in intent["allowed_tools"]
    assert "send_email" in intent["forbidden_tools"]
    assert body["latency_ms"] >= 0


def test_extract_rejects_empty_prompt() -> None:
    r = client.post("/v1/extract", json={"prompt": "   "})
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_extract_rejects_missing_prompt() -> None:
    r = client.post("/v1/extract", json={})
    # Pydantic missing-field validation = 422.
    assert r.status_code == 422


def test_extract_rejects_oversized_prompt() -> None:
    r = client.post("/v1/extract", json={"prompt": "x" * 9000})
    # Pydantic max_length=8000 → 422.
    assert r.status_code == 422
