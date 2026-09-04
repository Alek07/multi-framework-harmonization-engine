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

# The launcher is the single front door: it detects the hardware (NVIDIA -> AMD -> CPU),
# picks the matching overlay, and reports what it chose. Every target below delegates to
# it so `make` and the raw script can never disagree on how the stack comes up.
LAUNCH := ./scripts/start.sh

RUN_DIR := server/eval/runs
STAMP := $(shell date +%Y%m%d-%H%M%S)
ASSET ?=
E2E_ARGS := $(if $(ASSET),--asset $(ASSET),)

.PHONY: help up up-cpu up-gpu up-rocm build down logs e2e

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Start the stack, auto-detecting the hardware (NVIDIA -> AMD -> CPU)
	$(LAUNCH)

up-cpu: ## Start forcing the portable CPU path (the reproducible one)
	$(LAUNCH) --cpu

up-gpu: ## Start forcing the NVIDIA (CUDA) path
	$(LAUNCH) --gpu

up-rocm: ## Start forcing the AMD (ROCm, Linux only) path
	$(LAUNCH) --rocm

build: ## Rebuild images so code changes reach the containers, then start
	$(LAUNCH) --build

down: ## Stop the stack (volumes are kept)
	$(LAUNCH) --down

logs: ## Follow the logs of all services
	$(LAUNCH) --logs

# MSYS_NO_PATHCONV stops Git Bash rewriting the container path /tmp/... on Windows.
e2e: ## Run scripts/e2e_flow.py in the backend, dumping to server/eval/runs/
	@mkdir -p $(RUN_DIR)
	MSYS_NO_PATHCONV=1 $(COMPOSE) exec -T backend \
		python scripts/e2e_flow.py $(E2E_ARGS) --out /tmp/e2e-summary.json \
		| tee $(RUN_DIR)/console-$(STAMP).log
	@MSYS_NO_PATHCONV=1 docker cp $(BACKEND):/tmp/e2e-summary.json $(RUN_DIR)/summary-$(STAMP).json
	@echo "  → $(RUN_DIR)/console-$(STAMP).log"
	@echo "  → $(RUN_DIR)/summary-$(STAMP).json"
