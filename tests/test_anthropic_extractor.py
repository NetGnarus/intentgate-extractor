"""Tests for the AnthropicExtractor.

We don't call the real API in tests. Instead we mock the SDK's
`messages.create` response so the test exercises the JSON parsing, the
fallback-to-deny-most behavior on bad JSON, and the field coercion
through Pydantic.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.extractor import AnthropicExtractor


def _content(text: str) -> list[SimpleNamespace]:
    """Mimic the SDK's content-block list with a single text block."""
    return [SimpleNamespace(type="text", text=text)]


@pytest.fixture
def extractor() -> AnthropicExtractor:
    """Construct an AnthropicExtractor and replace its client."""
    e = AnthropicExtractor.__new__(AnthropicExtractor)
    e.model = "claude-haiku-4-5-20251001"
    e._client = MagicMock()
    return e


def test_extracts_well_formed_json(extractor: AnthropicExtractor) -> None:
    response = SimpleNamespace(
        content=_content(
            json.dumps(
                {
                    "summary": "Process AP invoices",
                    "allowed_tools": ["read_invoice", "record_in_ledger"],
                    "forbidden_tools": ["send_email", "transfer_funds"],
                    "confidence": 0.85,
                    "rationale": "test fixture",
                }
            )
        )
    )
    extractor._client.messages.create.return_value = response

    intent, latency = extractor.extract("Process today's AP invoices")

    assert intent.summary == "Process AP invoices"
    assert intent.allowed_tools == ["read_invoice", "record_in_ledger"]
    assert intent.forbidden_tools == ["send_email", "transfer_funds"]
    assert intent.confidence == 0.85
    assert latency >= 0


def test_falls_back_to_deny_most_on_invalid_json(extractor: AnthropicExtractor) -> None:
    extractor._client.messages.create.return_value = SimpleNamespace(
        content=_content("not valid json at all { ]")
    )
    intent, _ = extractor.extract("anything")

    # When the model gives us garbage we MUST fail closed: empty allow,
    # destructive tools forbidden.
    assert intent.allowed_tools == []
    assert "transfer_funds" in intent.forbidden_tools
    assert "send_email" in intent.forbidden_tools
    assert intent.confidence == 0.0
    assert intent.rationale and "non-JSON" in intent.rationale


def test_handles_missing_optional_fields(extractor: AnthropicExtractor) -> None:
    # Real models occasionally omit fields. Make sure we cope.
    extractor._client.messages.create.return_value = SimpleNamespace(
        content=_content(
            json.dumps(
                {
                    "summary": "Read an invoice",
                    "allowed_tools": ["read_invoice"],
                    # forbidden_tools, confidence, rationale all missing
                }
            )
        )
    )
    intent, _ = extractor.extract("read invoice 482")
    assert intent.allowed_tools == ["read_invoice"]
    assert intent.forbidden_tools == []
    assert 0.0 <= intent.confidence <= 1.0


def test_strips_markdown_fences_if_model_emits_them(extractor: AnthropicExtractor) -> None:
    # Some models like to wrap JSON in ```json fences. Our parser
    # should still cope — currently we don't strip, so this test
    # documents the *current* behavior: fenced output fails JSON parse
    # and we fall back to deny-most. Future work: strip the fences.
    extractor._client.messages.create.return_value = SimpleNamespace(
        content=_content(
            "```json\n"
            + json.dumps({"summary": "x", "allowed_tools": ["a"]})
            + "\n```"
        )
    )
    intent, _ = extractor.extract("anything")
    # Falls back; this isn't ideal but it's safe.
    assert intent.allowed_tools == []
