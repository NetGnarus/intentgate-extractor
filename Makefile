.PHONY: install dev run test docker docker-run smoke clean

PORT  ?= 8090
IMAGE ?= intentgate/extractor:dev

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"

# Run with auto-reload for local dev. Stub mode by default — no API key needed.
dev:
	EXTRACTOR_STUB=true .venv/bin/uvicorn app.main:app --reload --port $(PORT)

# Run without auto-reload, default mode (anthropic if ANTHROPIC_API_KEY set).
run:
	.venv/bin/uvicorn app.main:app --port $(PORT)

test:
	.venv/bin/pytest -q

docker:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p $(PORT):$(PORT) -e EXTRACTOR_STUB=true $(IMAGE)

# Smoke test: extractor running on $(PORT).
smoke:
	@echo '--- GET /healthz'
	@curl -sf http://localhost:$(PORT)/healthz | (jq . 2>/dev/null || cat); echo
	@echo '--- POST /v1/extract (Process AP invoices)'
	@curl -sX POST http://localhost:$(PORT)/v1/extract \
		-H 'Content-Type: application/json' \
		-d '{"prompt":"Process today AP invoices","agent_id":"finance-copilot-v3"}' \
		| (jq . 2>/dev/null || cat); echo
	@echo '--- POST /v1/extract (research request)'
	@curl -sX POST http://localhost:$(PORT)/v1/extract \
		-H 'Content-Type: application/json' \
		-d '{"prompt":"Research vendor Globex Logistics","agent_id":"vendor-onboarder-v2"}' \
		| (jq . 2>/dev/null || cat); echo

clean:
	rm -rf .venv __pycache__ */__pycache__ .pytest_cache *.egg-info
