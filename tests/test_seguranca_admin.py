import base64

import pytest
from app.config import Config
from app.main_admin import criar_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.conftest import CABECALHO_ADMIN, SENHA_TESTE, configurar_dependencias
from tests.helpers import NotificadorFalso


def _basic(usuario: str, senha: str) -> dict[str, str]:
    token = base64.b64encode(f"{usuario}:{senha}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


ROTAS_PROTEGIDAS = ["/", "/clientes", "/agendamentos", "/docs", "/openapi.json", "/app.js"]


@pytest.mark.parametrize("caminho", ROTAS_PROTEGIDAS)
def test_sem_credencial_retorna_401_com_desafio(app_admin: FastAPI, caminho: str):
    resposta = TestClient(app_admin).get(caminho)

    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"].startswith("Basic")


@pytest.mark.parametrize("caminho", ROTAS_PROTEGIDAS)
def test_com_credencial_correta_retorna_200(app_admin: FastAPI, caminho: str):
    resposta = TestClient(app_admin).get(caminho, headers=CABECALHO_ADMIN)

    assert resposta.status_code == 200


@pytest.mark.parametrize(
    "cabecalho",
    [
        _basic("admin", "senha-errada"),
        _basic("outro", SENHA_TESTE),
        _basic("admin", ""),
        _basic("", ""),
        {"Authorization": "Basic !!!nao-e-base64!!!"},
        {"Authorization": "Basic " + base64.b64encode(b"sem-dois-pontos").decode()},
        {"Authorization": "Bearer abc"},
        {"Authorization": ""},
    ],
    ids=[
        "senha",
        "usuario",
        "senha-vazia",
        "tudo-vazio",
        "base64-invalido",
        "sem-separador",
        "outro-esquema",
        "vazio",
    ],
)
def test_credenciais_invalidas_retornam_401(app_admin: FastAPI, cabecalho: dict):
    resposta = TestClient(app_admin).get("/clientes", headers=cabecalho)

    assert resposta.status_code == 401


def test_senha_com_dois_pontos_e_acentos_funciona(engine: Engine):
    aplicacao = configurar_dependencias(criar_app("se:nha-çã"), engine, NotificadorFalso())

    resposta = TestClient(aplicacao).get("/openapi.json", headers=_basic("admin", "se:nha-çã"))

    assert resposta.status_code == 200


def test_escrita_sem_credencial_e_bloqueada_antes_de_chegar_ao_servico(app_admin: FastAPI):
    resposta = TestClient(app_admin).post(
        "/clientes",
        json={"nome": "Carlos Silva", "email": "c@exemplo.com", "telefone": "11987654321"},
    )

    assert resposta.status_code == 401


def test_sem_senha_configurada_a_area_da_empresa_nao_sobe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.main_admin.CONFIG", Config(admin_password=None))

    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        criar_app()


def test_usa_a_senha_da_configuracao_quando_nao_recebe_argumento(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
):
    monkeypatch.setattr("app.main_admin.CONFIG", Config(admin_password="da-configuracao"))

    aplicacao = configurar_dependencias(criar_app(), engine, NotificadorFalso())

    cliente = TestClient(aplicacao)
    certa = cliente.get("/openapi.json", headers=_basic("admin", "da-configuracao"))
    errada = cliente.get("/openapi.json", headers=_basic("admin", "outra"))

    assert certa.status_code == 200
    assert errada.status_code == 401


def test_area_do_cliente_nao_pede_senha(client_publico: TestClient):
    assert client_publico.get("/servicos").status_code == 200
    assert client_publico.get("/").status_code == 200


def test_pagina_da_empresa_com_credencial(client: TestClient):
    pagina = client.get("/")

    assert pagina.status_code == 200
    assert "Painel da Empresa" in pagina.text
    assert "Marque seu horário" not in pagina.text
    assert "javascript" in client.get("/comum/util.js").headers["content-type"]
