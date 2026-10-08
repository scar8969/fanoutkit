# message_pusher - developer entry points. Every target is runnable offline.
PYTHON ?= python
VENV   ?= .venv
BIN    := $(VENV)/Scripts
ifeq ($(OS),)
  BIN := $(VENV)/bin
endif
PIP    := $(BIN)/pip
PY     := $(BIN)/python

.PHONY: help install fmt lint type test cov check run clean docker-build docker-run

help: ## Show this help
	@grep -hE "^[a-z-]+:.*?## " $(MAKEFILE_LIST) | awk "BEGIN{FS=\":.*?## \"}{printf \"  %-14s %s\n\", $$1, $$2}"

install: ## Create the virtualenv and install dev dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

fmt: ## Auto-format (ruff is required; see requirements-dev.txt)
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests

lint: ## Lint without modifying anything
	$(BIN)/ruff check src tests

type: ## Static type check
	$(BIN)/mypy src

test: ## Run the test suite
	$(PY) -m pytest

cov: ## Run the test suite with coverage and enforce the floor
	$(PY) -m pytest --cov --cov-report=term-missing --cov-report=xml

check: lint type cov ## The gate CI runs

run: ## Start the development server
	$(PY) wsgi.py

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

docker-build: ## Build the container image
	docker build -t message_pusher:dev .

docker-run: ## Run the container on port 8000
	docker run --rm -p 8000:8000 --env-file .env message_pusher:dev
