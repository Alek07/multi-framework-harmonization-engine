# On Windows, point make at Git Bash or it falls back to cmd.exe (no grep/awk/tee).
ifeq ($(OS),Windows_NT)
SHELL := $(firstword $(wildcard C:/PROGRA~1/Git/bin/bash.exe C:/PROGRA~1/Git/usr/bin/bash.exe) bash)
else
SHELL := bash
endif
.SHELLFLAGS := -o pipefail -c
.DEFAULT_GOAL := help

PROJECT := tfm-harmonization-engine
BACKEND := $(PROJECT)-backend
COMPOSE := docker compose -f docker-compose.yml

GPU ?= 1
ifeq ($(GPU),1)
COMPOSE_UP := $(COMPOSE) -f docker-compose.gpu.yml
else
COMPOSE_UP := $(COMPOSE)
endif

RUN_DIR := server/eval/runs
STAMP := $(shell date +%Y%m%d-%H%M%S)
ASSET ?=
E2E_ARGS := $(if $(ASSET),--asset $(ASSET),)

.PHONY: help up up-cpu build down logs e2e

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Start the stack (GPU by default; GPU=0 for the CPU path)
	$(COMPOSE_UP) up -d

up-cpu: ## Start the stack forcing the CPU path
	@$(MAKE) up GPU=0

build: ## Rebuild images so code changes reach the containers
	$(COMPOSE_UP) up -d --build

down: ## Stop the stack (volumes are kept)
	$(COMPOSE) down

logs: ## Follow the logs of all services
	$(COMPOSE) logs -f

# MSYS_NO_PATHCONV stops Git Bash rewriting the container path /tmp/... on Windows.
e2e: ## Run scripts/e2e_flow.py in the backend, dumping to server/eval/runs/
	@mkdir -p $(RUN_DIR)
	MSYS_NO_PATHCONV=1 $(COMPOSE) exec -T backend \
		python scripts/e2e_flow.py $(E2E_ARGS) --out /tmp/e2e-summary.json \
		| tee $(RUN_DIR)/console-$(STAMP).log
	@MSYS_NO_PATHCONV=1 docker cp $(BACKEND):/tmp/e2e-summary.json $(RUN_DIR)/summary-$(STAMP).json
	@echo "  → $(RUN_DIR)/console-$(STAMP).log"
	@echo "  → $(RUN_DIR)/summary-$(STAMP).json"
