.DEFAULT_GOAL := help

DEV_COMPOSE := docker compose --env-file .env \
	-f docker/docker-compose.yml \
	-f docker/docker-compose.dev.yml
WEB_SERVICE := web
MANAGE := python manage.py

PYTHON ?= python
LOG_SERVICES ?=
PYTEST_ARGS ?=

.PHONY: help dev-up dev-down dev-build dev-logs dev-ps shell migrate makemigrations check test lint

help:
	@printf '%s\n' 'Usage: make <target> [VARIABLE=value]' ''
	@printf '  %-16s %s\n' \
		help 'Show this help' \
		dev-up 'Build and start the development stack in the background' \
		dev-down 'Stop and remove development containers, keeping named volumes' \
		dev-build 'Build the development images' \
		dev-logs 'Follow recent logs (optional LOG_SERVICES="web celery")' \
		dev-ps 'Show development container status' \
		shell 'Open a Django shell in the running web container' \
		migrate 'Apply migrations to the development database' \
		makemigrations 'Generate migration files in the checkout' \
		check 'Run Django system checks in the running web container' \
		test 'Run the default backend pytest suite (optional PYTEST_ARGS)' \
		lint 'Run backend Ruff and Bandit checks'
	@printf '%s\n' '' \
		'Compose targets use the root development .env (see docker/env/.env.development.example).' \
		'shell, migrate, makemigrations, and check require a running web container.' \
		'test and lint use host Python 3.12 with requirements/requirements-test.txt installed.' \
		'Activate that virtual environment or pass PYTHON=/path/to/venv/bin/python.'

dev-up:
	$(DEV_COMPOSE) up --build -d

dev-down:
	$(DEV_COMPOSE) down

dev-build:
	$(DEV_COMPOSE) build

dev-logs:
	$(DEV_COMPOSE) logs --follow --tail=100 $(LOG_SERVICES)

dev-ps:
	$(DEV_COMPOSE) ps

shell:
	$(DEV_COMPOSE) exec $(WEB_SERVICE) $(MANAGE) shell

migrate:
	$(DEV_COMPOSE) exec -T $(WEB_SERVICE) $(MANAGE) migrate --noinput

# The checkout is bind-mounted, so write migrations as the host user.
makemigrations:
	$(DEV_COMPOSE) exec --user "$$(id -u):$$(id -g)" $(WEB_SERVICE) $(MANAGE) makemigrations

check:
	$(DEV_COMPOSE) exec -T $(WEB_SERVICE) $(MANAGE) check

test:
	$(PYTHON) -W error -m pytest --ds=config.settings.test $(PYTEST_ARGS)

lint:
	$(PYTHON) -m ruff check apps config tests
	$(PYTHON) -m bandit -q -r apps config -x 'apps/**/tests/**,config/tests/**'
