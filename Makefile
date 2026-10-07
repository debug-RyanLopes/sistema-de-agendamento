ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
PYTHON ?= python
PY := .venv\Scripts\python
else
PYTHON ?= python3
PY := .venv/bin/python
endif

HOST ?= 127.0.0.1
PORT ?= 8000

.DEFAULT_GOAL := help
.PHONY: help install run seed test cov lint clean

help:
	@echo Comandos disponiveis:
	@echo   make install  - cria o .venv e instala as dependencias
	@echo   make run      - sobe a API em http://$(HOST):$(PORT)
	@echo                   front-end em /app/ e Swagger em /docs
	@echo   make seed     - popula o banco com dados de exemplo
	@echo   make test     - roda os testes
	@echo   make cov      - roda os testes com cobertura
	@echo   make lint     - roda o ruff
	@echo   make clean    - remove caches e o arquivo .coverage
	@echo Opcoes: HOST=0.0.0.0 PORT=9000 make run

.venv:
	$(PYTHON) -m venv .venv

install: .venv
	$(PY) -m pip install -q -r requirements.txt ruff

run: install
	$(PY) -m uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

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
