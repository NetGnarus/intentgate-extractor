"""Tests for the offline StubExtractor.

These tests don't touch Anthropic — they exercise the heuristic rules
so we can be confident the stub mode is sane for local dev.
"""

from __future__ import annotations

from app.extractor import StubExtractor
from app.models import ExtractedIntent


def test_invoice_rule_matches() -> None:
    s = StubExtractor()
    intent, latency = s.extract("Process today's AP invoices")
    assert isinstance(intent, ExtractedIntent)
    assert "read_invoice" in intent.allowed_tools
    assert "record_in_ledger" in intent.allowed_tools
    assert "send_email" in intent.forbidden_tools
    assert "transfer_funds" in intent.forbidden_tools
    assert intent.confidence > 0
    assert latency >= 0


def test_research_rule_matches() -> None:
    s = StubExtractor()
    intent, _ = s.extract("Research vendor Globex Logistics")
    assert "web_search" in intent.allowed_tools
    assert "fetch_company_data" in intent.allowed_tools
    assert "transfer_funds" in intent.forbidden_tools


def test_pay_rule_includes_transfer_funds() -> None:
    s = StubExtractor()
    intent, _ = s.extract("Pay invoice 0482 from Globex")
    # Pay intent allows transfer_funds — that's the whole point.
    assert "transfer_funds" in intent.allowed_tools
    assert "send_email" in intent.forbidden_tools


def test_no_rule_match_defaults_to_deny_most() -> None:
    s = StubExtractor()
    intent, _ = s.extract("Tell me a joke about geese")
    assert intent.allowed_tools == []
    # Conservative deny-most for unknown intents.
    assert "transfer_funds" in intent.forbidden_tools
    assert "send_email" in intent.forbidden_tools
    assert intent.confidence < 0.5


def test_summary_is_set_to_user_input() -> None:
    s = StubExtractor()
    intent, _ = s.extract("Process today's AP invoices.")
    # Summary should reflect the user prompt; trailing punctuation is
    # normalized by the stub.
    assert "Process today" in intent.summary
