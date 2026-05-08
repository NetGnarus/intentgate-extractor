"""Core intent extraction logic.

Two implementations:

- :class:`StubExtractor`     — keyword-heuristic extractor; no LLM call,
                               no API key, fully offline. Useful for
                               local dev, CI, and when ``EXTRACTOR_STUB``
                               is set.
- :class:`AnthropicExtractor` — calls Claude Haiku with a structured
                               output prompt. Requires ANTHROPIC_API_KEY.

The two share a Protocol so the FastAPI app can swap them at startup.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Protocol

from .models import ExtractedIntent

logger = logging.getLogger(__name__)


class IntentExtractor(Protocol):
    """The contract the FastAPI app depends on."""

    name: str
    model: str

    def extract(self, prompt: str) -> tuple[ExtractedIntent, int]:
        """Return (intent, latency_ms) for the given prompt."""
        ...


# ---------------------------------------------------------------------------
# Stub extractor (offline)
# ---------------------------------------------------------------------------


class StubExtractor:
    """Heuristic extractor for offline dev.

    Recognizes a small set of finance-y keywords and returns a sensible
    allowlist. Not safe for production — no actual semantic
    understanding — but lets the gateway exercise the full intent flow
    without an API key or network call.
    """

    name = "stub"
    model = "stub-v1"

    # Hand-tuned mapping from intent keyword to the tools that intent
    # plausibly needs. The gateway never trusts these as policy; they
    # only let us round-trip the intent flow during dev.
    #
    # Order matters: rules are evaluated top-to-bottom and the first
    # match wins. "Pay an invoice" should bind to the pay rule (which
    # allows transfer_funds), not the read-only invoice rule, so
    # pay/transfer/wire is checked first.
    _RULES: list[tuple[tuple[str, ...], list[str], list[str]]] = [
        (
            ("pay ", "transfer", "wire"),
            ["read_invoice", "verify_vendor", "transfer_funds"],
            ["send_email", "export", "delete"],
        ),
        (
            ("research", "look up", "find vendor", "vendor information"),
            ["web_search", "fetch_company_data"],
            ["write_to_vendor_list", "transfer_funds", "send_email"],
        ),
        (
            ("invoice", "ap ", "accounts payable", "process today"),
            ["read_invoice", "record_in_ledger", "verify_vendor"],
            ["send_email", "transfer_funds", "delete", "export"],
        ),
        (
            ("reconcile", "balance"),
            ["read_invoice", "read_ledger", "compare_records"],
            ["send_email", "transfer_funds", "delete"],
        ),
    ]

    def extract(self, prompt: str) -> tuple[ExtractedIntent, int]:
        start = time.monotonic()
        p = prompt.lower()
        for keywords, allow, forbid in self._RULES:
            if any(k in p for k in keywords):
                intent = ExtractedIntent(
                    summary=prompt.strip().rstrip(".") + " [stub]",
                    allowed_tools=list(allow),
                    forbidden_tools=list(forbid),
                    confidence=0.6,
                    rationale=f"stub rule matched on {keywords[0]!r}",
                )
                return intent, int((time.monotonic() - start) * 1000)
        # Default: no specific intent recognized, conservative deny-most.
        intent = ExtractedIntent(
            summary=prompt.strip()[:200] + " [stub: no rule matched]",
            allowed_tools=[],
            forbidden_tools=["transfer_funds", "send_email", "delete", "export"],
            confidence=0.2,
            rationale="stub: no rule matched, defaulting to deny-most",
        )
        return intent, int((time.monotonic() - start) * 1000)


# ---------------------------------------------------------------------------
# Anthropic extractor (real LLM)
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You are an authorization assistant for an AI agent gateway.

Given a user's natural-language request to an AI agent, you produce a
structured JSON object describing the *narrowest* set of tools that
agent should be allowed to call to fulfill the request.

You MUST respond with a single JSON object, no prose, no markdown
fences. The object MUST have these fields:

  summary          one sentence, what the user is asking for
  allowed_tools    array of tool names the agent should be permitted
                   to call. Be conservative: include only tools clearly
                   needed by the request.
  forbidden_tools  array of tool names that must be blocked even if a
                   policy elsewhere would allow them. Always include
                   destructive or exfiltrative tools that are not
                   clearly needed (e.g. send_email, transfer_funds,
                   delete, export) when the request does not require
                   them.
  confidence       float in [0,1], your certainty. 0.5 if you must guess.
  rationale        short string, your reasoning.

If the request is ambiguous or empty, return allowed_tools=[] and
explain in rationale.

Tool names are short snake_case identifiers like read_invoice,
send_email, transfer_funds, web_search, fetch_company_data,
record_in_ledger, verify_vendor, write_to_vendor_list, read_customer_list."""


class AnthropicExtractor:
    """Real extractor backed by Claude Haiku.

    The model is small and cheap (~$0.25 per million input tokens at
    time of writing). Each extraction is roughly 500 tokens in + 200
    tokens out, so a session of dev testing costs cents.
    """

    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        # Import lazily so the stub mode doesn't require the SDK.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self.model = model

    def extract(self, prompt: str) -> tuple[ExtractedIntent, int]:
        start = time.monotonic()
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        # The SDK returns a list of content blocks. We expect a single
        # text block containing JSON.
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        ).strip()

        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("LLM returned non-JSON, falling back to deny-most: %s", e)
            return (
                ExtractedIntent(
                    summary=prompt.strip()[:200],
                    allowed_tools=[],
                    forbidden_tools=["transfer_funds", "send_email", "delete", "export"],
                    confidence=0.0,
                    rationale=f"LLM returned non-JSON: {e!s}",
                ),
                int((time.monotonic() - start) * 1000),
            )

        # Coerce/validate via Pydantic so we get the same shape as stub.
        intent = ExtractedIntent(
            summary=str(obj.get("summary", "")),
            allowed_tools=list(obj.get("allowed_tools", [])),
            forbidden_tools=list(obj.get("forbidden_tools", [])),
            confidence=float(obj.get("confidence", 0.5)),
            rationale=obj.get("rationale"),
        )
        return intent, int((time.monotonic() - start) * 1000)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_extractor() -> IntentExtractor:
    """Construct an extractor from the environment.

    EXTRACTOR_STUB=true forces the stub regardless of API key. Otherwise
    we use the Anthropic extractor if ANTHROPIC_API_KEY is present, and
    fall back to the stub if not.
    """
    if os.getenv("EXTRACTOR_STUB", "").lower() == "true":
        logger.info("extractor: stub mode (EXTRACTOR_STUB=true)")
        return StubExtractor()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("extractor: ANTHROPIC_API_KEY not set, falling back to stub")
        return StubExtractor()
    model = os.getenv("EXTRACTOR_MODEL", "claude-haiku-4-5-20251001")
    logger.info("extractor: anthropic model=%s", model)
    return AnthropicExtractor(api_key=api_key, model=model)
