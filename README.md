# IntentGate Extractor

[![CI](https://github.com/NetGnarus/intentgate-extractor/actions/workflows/ci.yml/badge.svg)](https://github.com/NetGnarus/intentgate-extractor/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg)](pyproject.toml)
[![Container](https://img.shields.io/badge/ghcr.io-intentgate--extractor-2188ff.svg)](https://github.com/NetGnarus/intentgate-extractor/pkgs/container/intentgate-extractor)

A small FastAPI service that turns free-form user prompts into
structured intent the [IntentGate gateway](https://github.com/NetGnarus/intentgate-gateway)
uses for the **second of four checks**.

This is the open-source extractor (Apache 2.0). A commercial
fine-tuned extractor with the same `/v1/extract` interface lives in a
private repo and ships as a drop-in replacement container.

## Companion repositories

| Repo | Purpose |
| ---- | ------- |
| [intentgate-gateway](https://github.com/NetGnarus/intentgate-gateway) | Go gateway with the four-check pipeline. Calls this service for the intent check. |
| [intentgate-extractor](https://github.com/NetGnarus/intentgate-extractor) | Intent extractor (this repo). |
| [intentgate-sdk-python](https://github.com/NetGnarus/intentgate-sdk-python) | Python SDK for agents — three lines to call the gateway with typed exceptions per check. |
| [intentgate-helm](https://github.com/NetGnarus/intentgate-helm) | Helm chart that deploys the gateway, extractor, and Redis to a Kubernetes cluster. |

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

## Lint

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

CI runs both on every PR — see `.github/workflows/ci.yml`.

## Project layout

```
app/main.py        # FastAPI app, /healthz and /v1/extract
app/extractor.py   # StubExtractor and AnthropicExtractor + factory
app/models.py      # Pydantic request/response models
tests/             # pytest, mocked SDK responses
Dockerfile         # python:3.11-slim base, runs as non-root
Makefile           # install / dev / run / test / docker / smoke
.github/workflows/ # CI (ruff + pytest + docker build) and release (publish image to GHCR)
```

## Docker

Build locally:

```sh
make docker
make docker-run
```

Pull the official multi-arch image (linux/amd64, linux/arm64) from GHCR:

```sh
docker pull ghcr.io/netgnarus/intentgate-extractor:latest
docker run --rm -p 8090:8090 -e EXTRACTOR_STUB=true ghcr.io/netgnarus/intentgate-extractor:latest
```

Tagged images (`:v0.1.0`, `:v0.1`, `:0.1.0`) are published automatically
when a `vX.Y.Z` git tag is pushed — see `.github/workflows/release.yml`.

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

## Contributing

Apache 2.0 and welcomes community contributions. A formal `CONTRIBUTING.md`
is coming with the v0.1 → v1.0 polish pass. For now, please open an
issue to discuss any non-trivial change before sending a PR.

## Security

If you find a security vulnerability, please **do not** open a public
issue. Email security@netgnarus.com (or open a GitHub Security Advisory
on this repo) and we'll respond within two business days.
