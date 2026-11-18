"""A área pública tem limite de agendamentos por cliente e de requisições por IP."""

import pytest
from app.config import Config
from app.dependencies import get_agora, get_db
from app.main_cliente import criar_app
from app.services import agendamento_service
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import Cenario
from tests.helpers import AGORA_FIXO, na_segunda


def _corpo(cenario: Cenario, inicio, **extras) -> dict:
    return {
        "nome": "Maria Nova",
        "email": "maria@exemplo.com",
        "telefone": "11911112222",
        "barbeiro_id": cenario.barbeiro.id,
        "servico_id": cenario.servico_30.id,
        "inicio": inicio.isoformat(),
        **extras,
    }


def test_limite_de_agendamentos_ativos_por_email(client_publico: TestClient, cenario: Cenario):
    respostas = [
        client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(9 + i)))
        for i in range(4)
    ]

    assert [r.status_code for r in respostas] == [201, 201, 201, 422]
    assert "já tem 3 horários" in respostas[3].json()["detail"]


def test_limite_vale_tambem_pelo_telefone(client_publico: TestClient, cenario: Cenario):
    for i in range(3):
        client_publico.post(
            "/agendamentos", json=_corpo(cenario, na_segunda(9 + i), email=f"m{i}@exemplo.com")
        )

    resposta = client_publico.post(
        "/agendamentos", json=_corpo(cenario, na_segunda(14), email="outro@exemplo.com")
    )

    assert resposta.status_code == 422


def test_cancelar_libera_uma_vaga_no_limite(client_publico: TestClient, cenario: Cenario):
    confirmacoes = [
        client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(9 + i))).json()
        for i in range(3)
    ]
    client_publico.post(
        f"/agendamentos/{confirmacoes[0]['id']}/cancelar",
        json={"codigo": confirmacoes[0]["codigo_cancelamento"]},
    )

    resposta = client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(14)))

    assert resposta.status_code == 201


def test_limite_zero_desativa_a_regra(
    client_publico: TestClient, cenario: Cenario, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        agendamento_service, "CONFIG", Config(max_agendamentos_ativos_por_cliente=0)
    )

    respostas = [
        client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(9 + i)))
        for i in range(5)
    ]

    assert all(r.status_code == 201 for r in respostas)


def test_agendamentos_da_empresa_nao_tem_limite(client: TestClient, cenario_api: dict[str, int]):
    respostas = [
        client.post(
            "/agendamentos",
            json={
                "cliente_id": cenario_api["cliente_id"],
                "barbeiro_id": cenario_api["barbeiro_id"],
                "servico_id": cenario_api["servico_30_id"],
                "inicio": na_segunda(9 + i).isoformat(),
            },
        )
        for i in range(5)
    ]

    assert all(r.status_code == 201 for r in respostas)


def test_cliente_inativo_recebe_mensagem_generica(
    client_publico: TestClient, session: Session, cenario: Cenario
):
    cenario.cliente.ativo = False
    session.commit()

    resposta = client_publico.post(
        "/agendamentos", json=_corpo(cenario, na_segunda(10), email=cenario.cliente.email)
    )

    assert resposta.status_code == 422
    assert "inativo" not in resposta.json()["detail"]
    assert "procure a barbearia" in resposta.json()["detail"]


@pytest.fixture
def app_limitado(engine, notificador) -> FastAPI:
    aplicacao = criar_app(limite_por_minuto=2)
    aplicacao.dependency_overrides[get_db] = lambda: (yield Session(engine))
    aplicacao.dependency_overrides[get_agora] = lambda: AGORA_FIXO
    return aplicacao


def test_limite_de_requisicoes_por_ip(app_limitado: FastAPI, cenario: Cenario):
    cliente = TestClient(app_limitado)
    corpo = _corpo(cenario, na_segunda(10))

    primeira = cliente.post("/agendamentos", json=corpo)
    segunda = cliente.post("/agendamentos", json=corpo)
    terceira = cliente.post("/agendamentos", json=corpo)
    leitura = cliente.get("/servicos")

    assert primeira.status_code == 201
    assert segunda.status_code == 409  # mesmo horário
    assert terceira.status_code == 429
    assert terceira.headers["retry-after"] == "60"
    assert leitura.status_code == 200  # leituras não contam


def test_limite_por_ip_separa_clientes_pelo_x_forwarded_for(app_limitado: FastAPI):
    cliente = TestClient(app_limitado)

    for _ in range(2):
        cliente.post("/agendamentos", json={}, headers={"X-Forwarded-For": "10.0.0.1"})
    bloqueado = cliente.post("/agendamentos", json={}, headers={"X-Forwarded-For": "10.0.0.1"})
    outro = cliente.post("/agendamentos", json={}, headers={"X-Forwarded-For": "10.0.0.2"})

    assert bloqueado.status_code == 429
    assert outro.status_code == 422  # passou pelo limite e caiu na validação do corpo


def test_limite_zero_desliga_o_controle_de_requisicoes(engine, notificador):
    aplicacao = criar_app(limite_por_minuto=0)
    aplicacao.dependency_overrides[get_db] = lambda: (yield Session(engine))
    cliente = TestClient(aplicacao)

    respostas = [cliente.post("/agendamentos", json={}) for _ in range(5)]

    assert all(r.status_code == 422 for r in respostas)
