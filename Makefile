ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
PYTHON ?= python
PY := .venv\Scripts\python
else
PYTHON ?= python3
PY := .venv/bin/python
endif

# Variáveis do .env (se existir) valem como padrão; a linha de comando sobrepõe.
-include .env
export

HOST ?= 127.0.0.1
PORTA_CLIENTE ?= 8000
PORTA_ADMIN ?= 8001
ADMIN_PASSWORD ?= admin123
export ADMIN_PASSWORD
export HOST
export PORTA_CLIENTE
export PORTA_ADMIN

.DEFAULT_GOAL := help
.PHONY: help install run run-cliente run-admin seed test e2e cov lint format clean

help:
	@echo Comandos disponiveis:
	@echo   make install      - cria o .venv e instala as dependencias
	@echo   make run          - sobe as DUAS areas ao mesmo tempo
	@echo   make run-cliente  - so a area do cliente: http://$(HOST):$(PORTA_CLIENTE)/
	@echo   make run-admin    - so a area da empresa: http://$(HOST):$(PORTA_ADMIN)/
	@echo                       usuario admin, senha $(ADMIN_PASSWORD) - so para desenvolvimento
	@echo   make seed         - popula o banco com dados de exemplo
	@echo   make test         - roda os testes
	@echo   make e2e          - testes de navegador (precisa do Google Chrome)
	@echo   make cov          - roda os testes com cobertura
	@echo   make lint         - roda o ruff (lint e formatacao)
	@echo   make format       - formata o codigo com o ruff
	@echo   make clean        - remove caches e o arquivo .coverage
	@echo Opcoes: PORTA_CLIENTE=9000 PORTA_ADMIN=9001 ADMIN_PASSWORD=outra make run

.venv:
	$(PYTHON) -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 'Este projeto exige Python 3.10 ou superior; use PYTHON=python3.13 make install')"
	$(PYTHON) -m venv .venv

install: .venv
	$(PY) -m pip install -q -r requirements-dev.txt

run: install
	$(PY) -m scripts.dev

run-cliente: install
	$(PY) -m uvicorn app.main_cliente:criar_app --factory --reload --host $(HOST) --port $(PORTA_CLIENTE)

run-admin: install
	$(PY) -m uvicorn app.main_admin:criar_app --factory --reload --host $(HOST) --port $(PORTA_ADMIN)

seed: install
	$(PY) -m scripts.seed

test: install
	$(PY) -m pytest

e2e: install
	$(PY) -m pytest -m e2e

cov: install
	$(PY) -m pytest --cov

lint: install
	$(PY) -m ruff check
	$(PY) -m ruff format --check app scripts tests

format: install
	$(PY) -m ruff format app scripts tests

clean:
	$(PY) -c "import pathlib, shutil; [shutil.rmtree(p, True) for d in ('app', 'scripts', 'tests') for p in pathlib.Path(d).rglob('__pycache__')]; [shutil.rmtree(d, True) for d in ('.pytest_cache', '.ruff_cache')]; pathlib.Path('.coverage').unlink(missing_ok=True)"
