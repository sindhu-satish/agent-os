UV ?= uv

.PHONY: install lint format typecheck test test-unit test-integration up down

install:
	$(UV) sync --dev

lint:
	$(UV) run ruff check src tests examples

format:
	$(UV) run ruff format src tests examples

typecheck:
	$(UV) run mypy src

test-unit:
	$(UV) run pytest tests/unit -q

test-integration:
	$(UV) run pytest tests/integration -q

test: test-unit

up:
	docker compose up -d postgres nats

down:
	docker compose down
