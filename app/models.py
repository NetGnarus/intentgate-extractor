"""Pydantic request/response models for the extractor service.

These define the on-the-wire contract between the gateway and the
extractor. They are deliberately small — the gateway is the policy
authority; the extractor only proposes structured intent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    """Inbound request to /v1/extract.

    The prompt is whatever the user said to the agent in natural
    language ("Process today's AP invoices", "Reconcile this account",
    etc). The agent is the calling agent's identifier so the gateway can
    pin the extracted intent to a specific agent in the audit log.
    """

    prompt: str = Field(..., min_length=1, max_length=8000)
    agent_id: str | None = Field(default=None, max_length=200)


class ExtractedIntent(BaseModel):
    """Structured intent returned by /v1/extract.

    summary is a one-line restatement of the user's request, suitable
    for human review and audit logs. allowed_tools is the *positive*
    set the agent may invoke; forbidden_tools is the *negative* set
    that must be blocked even if some upstream policy allows them.
    confidence is the model's self-reported certainty (0.0 to 1.0);
    callers can use it to flag low-confidence extractions for review.
    """

    summary: str
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str | None = None


class ExtractResponse(BaseModel):
    """Outbound response from /v1/extract."""

    intent: ExtractedIntent
    model: str = "stub"
    latency_ms: int = 0


class HealthResponse(BaseModel):
    status: str = "ok"
    mode: str = "stub"
    model: str | None = None
