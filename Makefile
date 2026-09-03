DC := docker compose
.DEFAULT_GOAL := help

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

bootstrap: ## First run: build, start, migrate, seed
	$(DC) up -d --build
	$(MAKE) migrate seed

up: ## Start the stack
	$(DC) up

down: ## Stop the stack
	$(DC) down

logs: ## Tail logs
	$(DC) logs -f

migrate: ## Apply migrations
	$(DC) run --rm backend uv run alembic upgrade head

migration: ## Create a migration: make migration name="add foo"
	$(DC) run --rm backend uv run alembic revision --autogenerate -m "$(name)"

seed: ## Load placeholder lookup data
	$(DC) run --rm backend uv run python -m app.seeds.seed_lookups

test: test-backend test-frontend ## Run all tests

test-backend: ## Backend tests
	$(DC) run --rm backend uv run pytest

test-frontend: ## Frontend tests
	$(DC) run --rm frontend npm run test

lint: ## Lint + type-check
	pre-commit run --all-files
	$(DC) run --rm backend uv run mypy app

format: ## Auto-fix formatting
	$(DC) run --rm backend uv run ruff format .
	$(DC) run --rm backend uv run ruff check --fix .
	$(DC) run --rm frontend npm run lint -- --fix

shell-backend: ## Shell into the backend container
	$(DC) run --rm backend bash

psql: ## psql into the database
	$(DC) exec db sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

.PHONY: help bootstrap up down logs migrate migration seed test test-backend \
        test-frontend lint format shell-backend psql
