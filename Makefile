# /!\ /!\ /!\ /!\ /!\ /!\ /!\ DISCLAIMER /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\
#
# This Makefile is only meant to be used for DEVELOPMENT purpose as we are
# changing the user id that will run in the container.
#
# PLEASE DO NOT USE IT FOR YOUR CI/PRODUCTION/WHATEVER...
#
# /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\ /!\
#
# Note to developers:
#
# While editing this file, please respect the following statements:
#
# 1. Every variable should be defined in the ad hoc VARIABLES section with a
#    relevant subsection
# 2. Every new rule should be defined in the ad hoc RULES section with a
#    relevant subsection depending on the targeted service
# 3. Rules should be sorted alphabetically within their section
# 4. When a rule has multiple dependencies, you should:
#    - duplicate the rule name to add the help string (if required)
#    - write one dependency per line to increase readability and diffs
# 5. .PHONY rule statement should be written after the corresponding rule
# ==============================================================================
# VARIABLES

BOLD := \033[1m
RESET := \033[0m
GREEN := \033[1;32m


# -- Docker
# Get the current user ID to use for docker run and docker exec commands
DOCKER_UID          = $(shell id -u)
DOCKER_GID          = $(shell id -g)
DOCKER_USER         = $(DOCKER_UID):$(DOCKER_GID)
COMPOSE             = DOCKER_USER=$(DOCKER_USER) docker compose
COMPOSE_EXEC        = $(COMPOSE) exec
COMPOSE_EXEC_APP    = $(COMPOSE_EXEC) app
COMPOSE_RUN         = $(COMPOSE) run --rm
COMPOSE_RUN_APP     = $(COMPOSE_RUN) app

# -- Backend
MANAGE              = $(COMPOSE_RUN_APP) python manage.py

# ==============================================================================
# RULES

default: help

data/opensearch:
	@mkdir -p data/opensearch

data/static:
	@mkdir -p data/static

# -- Project

create-env-files: ## Copy the dist env files to env files
create-env-files: \
	env.d/development/common
.PHONY: create-env-files

bootstrap: ## Prepare Docker images for the project
bootstrap: \
	data/opensearch \
	data/static \
	create-env-files \
	build \
	demo
.PHONY: bootstrap

# -- Docker/compose
build: ## build the app container
	@$(COMPOSE) build app --no-cache
.PHONY: build

down: ## stop and remove containers, networks, images, and volumes
	@$(COMPOSE) down
.PHONY: down

logs: ## display app logs (follow mode)
	@$(COMPOSE) logs -f app
.PHONY: logs

run: ## start the wsgi (production) and development server
	@$(COMPOSE) up --force-recreate -d celery
.PHONY: run

status: ## an alias for "docker compose ps"
	@$(COMPOSE) ps
.PHONY: status

stop: ## stop the development server using Docker
	@$(COMPOSE) stop
.PHONY: stop

# -- Backend

demo: ## create a demo for load testing purpose
	@$(MANAGE) create_demo
.PHONY: demo

# Nota bene: Black should come after isort just in case they don't agree...
lint: ## lint back-end python sources
lint: \
  lint-ruff-format \
  lint-ruff-check \
  lint-pylint
.PHONY: lint

lint-ruff-format: ## format back-end python sources with ruff
	@echo 'lint:ruff-format started…'
	@$(COMPOSE_RUN_APP) ruff format .
.PHONY: lint-ruff-format

lint-ruff-check: ## lint back-end python sources with ruff
	@echo 'lint:ruff-check started…'
	@$(COMPOSE_RUN_APP) ruff check . --fix
.PHONY: lint-ruff-check

lint-pylint: ## lint back-end python sources with pylint only on changed files from main
	@echo 'lint:pylint started…'
	bin/pylint .
.PHONY: lint-pylint

pre-commit-install: ## install pre-commit hooks
	@pre-commit install --install-hooks -t pre-commit -t commit-msg
.PHONY: pre-commit-install

test: ## run project tests
	@$(MAKE) test-back-parallel
.PHONY: test

test-back: ## run back-end tests
	@args="$(filter-out $@,$(MAKECMDGOALS))" && \
	bin/pytest $${args:-${1}}
.PHONY: test-back

test-back-parallel: ## run all back-end tests in parallel
	@args="$(filter-out $@,$(MAKECMDGOALS))" && \
	bin/pytest -n auto $${args:-${1}}
.PHONY: test-back-parallel



shell: ## open Django interactive shell
	@$(MANAGE) shell #_plus
.PHONY: shell

env.d/development/common:
	cp --update=none env.d/development/common.dist env.d/development/common

# -- Misc
clean: ## restore repository state as it was freshly cloned
	git clean -idx
.PHONY: clean

help:
	@echo "$(BOLD)find Makefile"
	@echo "Please use 'make $(BOLD)target$(RESET)' where $(BOLD)target$(RESET) is one of:"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(firstword $(MAKEFILE_LIST)) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-30s$(RESET) %s\n", $$1, $$2}'
.PHONY: help

# -- K8S
build-k8s-cluster: ## build the kubernetes cluster using kind
	./bin/start-kind.sh
.PHONY: build-k8s-cluster

start-tilt: ## start the kubernetes cluster using kind
	tilt up -f ./bin/Tiltfile
.PHONY: build-k8s-cluster
