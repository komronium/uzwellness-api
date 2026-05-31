.PHONY: help install format lint test test-fast test-failed compile check alembic-heads migrate seed dev up down logs build

UV_CACHE_DIR ?= /tmp/uv-cache
TEST_DATABASE_URL ?= postgresql+asyncpg://sanotour:sanotour@localhost:5432/sanotour_test
DATABASE_URL ?= postgresql+asyncpg://sanotour:sanotour@localhost:5432/sanotour
REDIS_URL ?= redis://localhost:6379/0

help:
	@printf "Targets:\n"
	@printf "  install       Install dependencies\n"
	@printf "  format        Format code with Ruff\n"
	@printf "  lint          Run Ruff checks\n"
	@printf "  test          Run full test suite\n"
	@printf "  test-fast     Run latest focused tests\n"
	@printf "  test-failed   Re-run last failed tests\n"
	@printf "  compile       Compile app modules\n"
	@printf "  check         Lint, compile, Alembic heads, full tests\n"
	@printf "  migrate       Apply Alembic migrations\n"
	@printf "  seed          Seed initial super admin\n"
	@printf "  dev           Run local FastAPI dev server on port 8080\n"
	@printf "  up/down/logs  Docker compose helpers\n"

install:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv sync --dev

format:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run ruff format .

lint:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run ruff check .

test:
	UV_CACHE_DIR=$(UV_CACHE_DIR) TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest

test-fast:
	UV_CACHE_DIR=$(UV_CACHE_DIR) TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest tests/test_packages.py tests/test_rate_plans.py

test-failed:
	UV_CACHE_DIR=$(UV_CACHE_DIR) TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest --lf

compile:
	python -m compileall app

alembic-heads:
	@test "$$(UV_CACHE_DIR=$(UV_CACHE_DIR) DATABASE_URL=$(DATABASE_URL) uv run alembic heads | wc -l)" = "1"

check: lint compile alembic-heads test

migrate:
	UV_CACHE_DIR=$(UV_CACHE_DIR) DATABASE_URL=$(DATABASE_URL) uv run alembic upgrade head

seed:
	DATABASE_URL=$(DATABASE_URL) REDIS_URL=$(REDIS_URL) uv run python -m scripts.seed

dev:
	UV_CACHE_DIR=$(UV_CACHE_DIR) DATABASE_URL=$(DATABASE_URL) REDIS_URL=$(REDIS_URL) uv run fastapi dev app/main.py --port 8080

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f app

build:
	docker build -t uzwellness-api:local .
