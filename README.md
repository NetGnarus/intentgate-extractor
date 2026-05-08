# IntentGate Extractor

A small FastAPI service that turns free-form user prompts into
structured intent the gateway uses for the **second of four checks**.

License: **Apache 2.0**.

## What it does

```
POST /v1/extract
{
  "prompt":   "Process today's AP invoices",
  "agent_id": "finance-copilot-v3"
}
```

returns

```
{
  "intent": {
    "summary":         "Process today's AP invoices",
    "allowed_tools":   ["read_invoice", "record_in_ledger", "verify_vendor"],
    "forbidden_tools": ["send_email", "transfer_funds", "delete", "export"],
    "confidence":      0.6,
    "rationale":       "stub rule matched on 'invoice'"
  },
  "model":      "stub-v1",
  "latency_ms": 0
}
```

The gateway calls this endpoint once per session (cached), then checks
every tool call against `allowed_tools` / `forbidden_tools`.

## Two modes

**Stub mode** (`EXTRACTOR_STUB=true`). Heuristic, offline, no API key
required. Recognizes a small set of finance-y keywords and returns a
sensible allowlist. Useful for local dev and CI. Not safe for
production.

**Anthropic mode** (default, when `ANTHROPIC_API_KEY` is set). Calls
Claude Haiku with a structured-output system prompt. Costs roughly
fractions of a cent per extraction.

If `ANTHROPIC_API_KEY` is unset and `EXTRACTOR_STUB` is unset, the
service falls back to stub mode and logs a warning.

## Quick start

Requires Python 3.11+.

```sh
make install        # creates .venv and installs deps
make dev            # auto-reload, stub mode (no API key)
```

The service listens on `:8090` by default. Smoke-test it in another
shell:

```sh
make smoke
```

To use the real Anthropic-backed extractor:

```sh
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/uvicorn app.main:app --port 8090
```

## Tests

```sh
make test
```

Tests don't call the real API — they mock the SDK's response so the
test suite is fully offline.

## Configuration

| Env var               | Default                       | Description                                             |
| --------------------- | ----------------------------- | ------------------------------------------------------- |
| `EXTRACTOR_STUB`      | _unset_                       | Set to `true` to force the offline stub.                |
| `ANTHROPIC_API_KEY`   | _unset_                       | Required for Anthropic mode.                            |
| `EXTRACTOR_MODEL`     | `claude-haiku-4-5-20251001`   | Override the Claude model used.                         |
| `LOG_LEVEL`           | `INFO`                        | Python logging level.                                   |

## Project layout

```
app/main.py        # FastAPI app, /healthz and /v1/extract
app/extractor.py   # StubExtractor and AnthropicExtractor + factory
app/models.py      # Pydantic request/response models
tests/             # pytest, mocked SDK responses
Dockerfile         # python:3.11-slim base, runs as non-root
Makefile           # install / dev / run / test / docker / smoke
```

## Docker

```sh
make docker
make docker-run
```

## Why is this a separate service?

Three reasons.

1. **Different runtime, different scaling shape.** The gateway is hot
   (every tool call). The extractor is cold (once per session, cached).
   Different replica counts, different timeouts.
2. **LLM dependency isolated.** The gateway shouldn't link the
   Anthropic SDK or any LLM client. Keeps the gateway's binary tiny and
   its security review surface small.
3. **Future commercial swap.** The advanced intent extractor (with
   fine-tuned models) lives in a private repo and ships as a different
   container. The interface is the same `/v1/extract` shape, so the
   gateway never knows which extractor is running.
