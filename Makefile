ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
PYTHON ?= python
PY := .venv\Scripts\python
else
PYTHON ?= python3
PY := .venv/bin/python
endif

HOST ?= 127.0.0.1
PORTA_CLIENTE ?= 8000
PORTA_ADMIN ?= 8001
ADMIN_PASSWORD ?= admin123
export ADMIN_PASSWORD
export HOST
export PORTA_CLIENTE
export PORTA_ADMIN

.DEFAULT_GOAL := help
.PHONY: help install run run-cliente run-admin seed test cov lint clean

help:
	@echo Comandos disponiveis:
	@echo   make install      - cria o .venv e instala as dependencias
	@echo   make run          - sobe as DUAS areas ao mesmo tempo
	@echo   make run-cliente  - so a area do cliente: http://$(HOST):$(PORTA_CLIENTE)/
	@echo   make run-admin    - so a area da empresa: http://$(HOST):$(PORTA_ADMIN)/
	@echo                       usuario admin, senha $(ADMIN_PASSWORD) - so para desenvolvimento
	@echo   make seed         - popula o banco com dados de exemplo
	@echo   make test         - roda os testes
	@echo   make cov          - roda os testes com cobertura
	@echo   make lint         - roda o ruff
	@echo   make clean        - remove caches e o arquivo .coverage
	@echo Opcoes: PORTA_CLIENTE=9000 PORTA_ADMIN=9001 ADMIN_PASSWORD=outra make run

.venv:
	$(PYTHON) -m venv .venv

install: .venv
	$(PY) -m pip install -q -r requirements.txt ruff

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

cov: install
	$(PY) -m pytest --cov=app --cov-report=term-missing

lint: install
	$(PY) -m ruff check app scripts tests --select E,F,I,UP,B --line-length 99

clean:
	$(PY) -c "import pathlib, shutil; [shutil.rmtree(p, True) for d in ('app', 'scripts', 'tests') for p in pathlib.Path(d).rglob('__pycache__')]; [shutil.rmtree(d, True) for d in ('.pytest_cache', '.ruff_cache')]; pathlib.Path('.coverage').unlink(missing_ok=True)"
