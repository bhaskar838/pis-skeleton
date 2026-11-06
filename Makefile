# DCS-PIS — single entry point (SPEC §4.1 Monorepo, §17.11).
# Windows: install GNU make (`winget install ezwinports.make`) and run from Git Bash.

SHELL := bash
.ONESHELL:
.DEFAULT_GOAL := help
UV ?= uv
PNPM ?= pnpm
COMPOSE ?= docker compose
PYTEST := $(UV) run pytest -p no:cacheprovider

.PHONY: help env install dev up down reset seed logs ps test test-unit test-integration test-isolation test-e2e \
        test-web lint fmt typecheck codegen gate sbom scan

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

env: ## Create .env with random local secrets (never overwrites)
	python scripts/gen_env.py

install: ## Install Python (uv) and Node (pnpm) dependencies
	$(UV) sync
	$(PNPM) install

# ------------------------------------------------------------------------------------------- stack
dev: env ## Boot the whole local stack (builds images), wait until healthy
	mkdir -p apps/keycloak-theme/dist_keycloak
	$(COMPOSE) up -d --build --wait
	@echo "web http://localhost:3000 · admin http://localhost:3001 · keycloak http://keycloak.localhost:8080"
	@echo "mailpit http://localhost:8025 · temporal http://localhost:8088 · grafana http://localhost:3002"

up: dev ## Alias of dev

down: ## Stop the stack (keeps data)
	$(COMPOSE) down

reset: ## Stop the stack and DELETE all local data volumes
	$(COMPOSE) down -v --remove-orphans

seed: ## Seed local data (feature flags, demo staff note)
	$(COMPOSE) run --rm control-api python -m control_api.seed

logs: ## Tail service logs
	$(COMPOSE) logs -f --tail=100

ps: ## Service status
	$(COMPOSE) ps

# ------------------------------------------------------------------------------------------- tests
test: lint typecheck test-unit test-integration test-isolation test-web ## Everything CI runs (except e2e)

test-unit: ## Python unit tests with per-package coverage thresholds (SPEC §14.3)
	$(PYTEST) packages/py/dcs_authz -q --cov=dcs_authz --cov-branch --cov-fail-under=95
	$(PYTEST) packages/py/dcs_vault -q --cov=dcs_vault --cov-branch --cov-fail-under=95
	$(PYTEST) packages/py/dcs_common -q --cov=dcs_common --cov-branch --cov-fail-under=90
	$(PYTEST) services -q -m "not integration"

test-integration: ## Service integration tests (Docker required: testcontainers)
	$(PYTEST) services -q -W ignore::DeprecationWarning \
	  --cov=control_api --cov=data_api --cov=realtime_gw --cov-branch --cov-fail-under=80

test-isolation: ## Generated cross-tenant access tests (blocking)
	$(PYTEST) tests/isolation -q -W ignore::DeprecationWarning

test-web: ## Frontend unit tests
	$(PNPM) -r --if-present test

test-e2e: ## Playwright against a fresh compose stack (`make reset dev` first: the staff journey is a first login)
	set -a; . ./.env; set +a; E2E_STAFF_PASSWORD="$$DCS_KC_STAFF_PASSWORD" $(PNPM) --filter @dcs/e2e e2e

# ------------------------------------------------------------------------------------------- quality
lint: ## ruff + eslint
	$(UV) run ruff check packages services tests conftest.py
	$(UV) run ruff format --check packages services tests conftest.py
	$(PNPM) -r --if-present lint

fmt: ## Auto-format
	$(UV) run ruff format packages services tests conftest.py
	$(UV) run ruff check --fix packages services tests conftest.py
	$(PNPM) -r --if-present format

typecheck: ## mypy --strict + tsc --noEmit
	$(UV) run mypy -p dcs_common -p dcs_authz -p dcs_vault -p dcs_cbm -p control_api -p data_api -p realtime_gw
	$(PNPM) -r --if-present typecheck

codegen: ## Export OpenAPI specs and regenerate the TypeScript client
	$(UV) run python scripts/export_openapi.py
	$(PNPM) --filter @dcs/api-client generate

# ------------------------------------------------------------------------------------------- gates
gate: ## Run the phase gate suites: make gate PHASE=0
	@test -n "$(PHASE)" || (echo "usage: make gate PHASE=N" && exit 1)
	$(MAKE) test
	@echo "Fill docs/phases/PHASE_$(PHASE)_GATE.md with the evidence above (template: SPEC §17.10)."

sbom: ## SBOM for the Python image (needs syft)
	syft dcs-pis/python:local -o cyclonedx-json > sbom-python.json

scan: ## Vulnerability + secret scans (needs trivy, gitleaks)
	trivy fs --severity CRITICAL --exit-code 1 .
	gitleaks detect --no-banner --redact
