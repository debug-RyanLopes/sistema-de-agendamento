import pytest
from fastapi.testclient import TestClient


def test_pagina_inicial_e_servida(client: TestClient):
    resposta = client.get("/app/")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/html")
    assert "Agendamento de Barbearia" in resposta.text


@pytest.mark.parametrize(
    ("caminho", "tipo"),
    [("/app/app.js", "javascript"), ("/app/style.css", "css")],
)
def test_arquivos_estaticos_sao_servidos(client: TestClient, caminho: str, tipo: str):
    resposta = client.get(caminho)

    assert resposta.status_code == 200
    assert tipo in resposta.headers["content-type"]


def test_raiz_redireciona_para_o_front_end(client: TestClient):
    resposta = client.get("/", follow_redirects=False)

    assert resposta.status_code == 307
    assert resposta.headers["location"] == "/app/"


def test_front_end_nao_aparece_no_openapi(client: TestClient):
    caminhos = client.get("/openapi.json").json()["paths"]

    assert "/" not in caminhos
    assert not any(caminho.startswith("/app") for caminho in caminhos)
