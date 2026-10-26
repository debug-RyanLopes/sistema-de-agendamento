import logging
from datetime import datetime

import pytest
from app.dependencies import get_notificador
from app.services.notificacao_service import DadosConfirmacao, LogNotificador
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.helpers import AGORA_FIXO, DOMINGO, NotificadorFalso, NotificadorQuebrado, na_segunda


def _agendar(client: TestClient, cenario_api: dict[str, int], inicio: datetime, servico="30"):
    return client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api[f"servico_{servico}_id"],
            "inicio": inicio.isoformat(),
        },
    )


def test_at001_cria_agendamento_e_dispara_uma_confirmacao(
    client: TestClient, cenario_api: dict[str, int], notificador: NotificadorFalso
):
    resposta = _agendar(client, cenario_api, na_segunda(10))

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["fim"] == na_segunda(10, 30).isoformat()
    assert corpo["status"] == "agendado"
    assert len(notificador.enviados) == 1
    assert notificador.enviados[0].cliente == "Carlos Silva"
    assert notificador.enviados[0].barbeiro == "João Barbeiro"


@pytest.mark.parametrize(
    ("hora", "minuto", "servico"),
    [(10, 15, "30"), (10, 0, "30"), (9, 45, "30"), (9, 30, "60")],
    ids=["parcial", "total", "parcial-antes", "novo-envolve"],
)
def test_at002_sobreposicao_retorna_409_e_nao_grava(
    client: TestClient,
    cenario_api: dict[str, int],
    notificador: NotificadorFalso,
    hora: int,
    minuto: int,
    servico: str,
):
    _agendar(client, cenario_api, na_segunda(10))

    resposta = _agendar(client, cenario_api, na_segunda(hora, minuto), servico)

    assert resposta.status_code == 409
    assert client.get("/agendamentos").json()["total"] == 1
    assert len(notificador.enviados) == 1


def test_at003_intervalo_encostado_retorna_201(client: TestClient, cenario_api: dict[str, int]):
    _agendar(client, cenario_api, na_segunda(10))

    assert _agendar(client, cenario_api, na_segunda(10, 30)).status_code == 201


@pytest.mark.parametrize(
    "inicio",
    [na_segunda(18), DOMINGO.replace(hour=10), na_segunda(17, 45)],
    ids=["no-fim-da-janela", "domingo", "fim-excede-janela"],
)
def test_at004_fora_da_disponibilidade_retorna_422(
    client: TestClient, cenario_api: dict[str, int], inicio: datetime
):
    assert _agendar(client, cenario_api, inicio).status_code == 422


def test_at005_horario_no_passado_retorna_422(client: TestClient, cenario_api: dict[str, int]):
    assert _agendar(client, cenario_api, datetime(2029, 12, 31, 10, 0)).status_code == 422
    assert _agendar(client, cenario_api, AGORA_FIXO).status_code == 422


def test_at006_cancelar_libera_o_horario(client: TestClient, cenario_api: dict[str, int]):
    criado = _agendar(client, cenario_api, na_segunda(10)).json()

    cancelado = client.delete(f"/agendamentos/{criado['id']}")
    novo = _agendar(client, cenario_api, na_segunda(10))

    assert cancelado.status_code == 200
    assert cancelado.json()["status"] == "cancelado"
    assert novo.status_code == 201


@pytest.mark.parametrize("campo", ["cliente_id", "barbeiro_id", "servico_id"])
def test_at007_recurso_inexistente_retorna_404(
    client: TestClient, cenario_api: dict[str, int], campo: str
):
    corpo = {
        "cliente_id": cenario_api["cliente_id"],
        "barbeiro_id": cenario_api["barbeiro_id"],
        "servico_id": cenario_api["servico_30_id"],
        "inicio": na_segunda(10).isoformat(),
    }
    corpo[campo] = 999

    assert client.post("/agendamentos", json=corpo).status_code == 404


def test_at009_falha_na_notificacao_nao_afeta_a_resposta(
    app_admin: FastAPI,
    client: TestClient,
    cenario_api: dict[str, int],
    caplog: pytest.LogCaptureFixture,
):
    app_admin.dependency_overrides[get_notificador] = lambda: NotificadorQuebrado()

    with caplog.at_level(logging.ERROR, logger="notificacoes"):
        resposta = _agendar(client, cenario_api, na_segunda(10))

    assert resposta.status_code == 201
    assert "falha ao enviar confirmação" in caplog.text


def test_log_notificador_registra_uma_linha_com_os_dados(caplog: pytest.LogCaptureFixture):
    dados = DadosConfirmacao(
        email="carlos@exemplo.com",
        cliente="Carlos Silva",
        barbeiro="João Barbeiro",
        servico="Corte de cabelo",
        inicio=na_segunda(10),
        preco=45.0,
    )

    with caplog.at_level(logging.INFO, logger="notificacoes"):
        LogNotificador().enviar_confirmacao(dados)

    assert len(caplog.records) == 1
    mensagem = caplog.records[0].getMessage()
    for trecho in ("carlos@exemplo.com", "Carlos Silva", "João Barbeiro", "07/01/2030 10:00"):
        assert trecho in mensagem
    assert "45.00" in mensagem


def test_lista_filtra_e_obtem_agendamento(client: TestClient, cenario_api: dict[str, int]):
    criado = _agendar(client, cenario_api, na_segunda(10)).json()

    filtrado = client.get("/agendamentos", params={"barbeiro_id": cenario_api["barbeiro_id"]})
    por_dia = client.get("/agendamentos", params={"data": "2030-01-07"})
    outro_dia = client.get("/agendamentos", params={"data": "2030-01-08"})

    assert [item["id"] for item in filtrado.json()["itens"]] == [criado["id"]]
    assert por_dia.json()["total"] == 1
    assert outro_dia.json()["itens"] == []
    assert client.get(f"/agendamentos/{criado['id']}").json()["id"] == criado["id"]


def test_agendamento_inexistente_retorna_404(client: TestClient):
    assert client.get("/agendamentos/999").status_code == 404
    assert client.delete("/agendamentos/999").status_code == 404


def test_inicio_com_fuso_retorna_422(client: TestClient, cenario_api: dict[str, int]):
    corpo = {
        "cliente_id": cenario_api["cliente_id"],
        "barbeiro_id": cenario_api["barbeiro_id"],
        "servico_id": cenario_api["servico_30_id"],
        "inicio": "2030-01-07T10:00:00-03:00",
    }

    assert client.post("/agendamentos", json=corpo).status_code == 422


def test_swagger_e_openapi_expoem_todas_as_rotas(client: TestClient):
    esquema = client.get("/openapi.json").json()

    assert client.get("/docs").status_code == 200
    for rota in (
        "/clientes",
        "/barbeiros",
        "/servicos",
        "/barbeiros/{barbeiro_id}/disponibilidades",
        "/barbeiros/{barbeiro_id}/horarios-livres",
        "/agendamentos",
        "/agendamentos/{agendamento_id}",
    ):
        assert rota in esquema["paths"]
    respostas = esquema["paths"]["/agendamentos"]["post"]["responses"]
    assert {"201", "404", "409", "422"} <= set(respostas)
