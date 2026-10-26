from datetime import datetime

import pytest
from app.dependencies import get_agora
from app.models import Barbeiro
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import Cenario
from tests.helpers import DOMINGO, NotificadorFalso, na_segunda

ROTAS_ESPERADAS = {
    "/servicos",
    "/disponibilidade",
    "/agendamentos",
    "/agendamentos/{agendamento_id}/cancelar",
}


def _corpo(cenario: Cenario, inicio: datetime, **extras) -> dict:
    corpo = {
        "nome": "Maria Nova",
        "email": "maria@exemplo.com",
        "telefone": "11911112222",
        "barbeiro_id": cenario.barbeiro.id,
        "servico_id": cenario.servico_30.id,
        "inicio": inicio.isoformat(),
    }
    return {**corpo, **extras}


def test_area_do_cliente_expoe_somente_as_rotas_do_cliente(client_publico: TestClient):
    caminhos = client_publico.get("/openapi.json").json()["paths"]

    assert set(caminhos) == ROTAS_ESPERADAS


@pytest.mark.parametrize("caminho", ["/clientes", "/barbeiros", "/produtos", "/agendamentos/1"])
def test_rotas_da_empresa_nao_existem_na_area_do_cliente(client_publico: TestClient, caminho: str):
    assert client_publico.get(caminho).status_code == 404


def test_cliente_nao_consegue_cadastrar_nem_listar_agendamentos(client_publico: TestClient):
    assert client_publico.post("/clientes", json={}).status_code in (404, 405)
    assert client_publico.get("/agendamentos").status_code in (404, 405)
    assert client_publico.delete("/agendamentos/1").status_code in (404, 405)


def test_lista_somente_servicos_ativos(
    client_publico: TestClient, session: Session, cenario: Cenario
):
    cenario.servico_60.ativo = False
    session.commit()

    resposta = client_publico.get("/servicos")

    assert [servico["nome"] for servico in resposta.json()] == ["Corte de cabelo"]
    assert "ativo" not in resposta.json()[0]


def test_disponibilidade_mostra_barbeiros_com_horarios(
    client_publico: TestClient, cenario: Cenario
):
    resposta = client_publico.get(
        "/disponibilidade", params={"data": "2030-01-07", "servico_id": cenario.servico_30.id}
    )

    corpo = resposta.json()
    assert resposta.status_code == 200
    assert [barbeiro["nome"] for barbeiro in corpo["barbeiros"]] == ["João Barbeiro"]
    assert len(corpo["barbeiros"][0]["horarios"]) == 35


def test_disponibilidade_oculta_barbeiro_inativo_e_dia_sem_janela(
    client_publico: TestClient, session: Session, cenario: Cenario
):
    cenario.barbeiro.ativo = False
    session.commit()

    segunda = client_publico.get(
        "/disponibilidade", params={"data": "2030-01-07", "servico_id": cenario.servico_30.id}
    )
    domingo = client_publico.get(
        "/disponibilidade",
        params={"data": DOMINGO.date().isoformat(), "servico_id": cenario.servico_30.id},
    )

    assert segunda.json()["barbeiros"] == []
    assert domingo.json()["barbeiros"] == []


def test_disponibilidade_exclui_horario_ocupado(client_publico: TestClient, cenario: Cenario):
    client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(10)))

    resposta = client_publico.get(
        "/disponibilidade", params={"data": "2030-01-07", "servico_id": cenario.servico_30.id}
    )

    horarios = resposta.json()["barbeiros"][0]["horarios"]
    assert na_segunda(10).isoformat() not in horarios
    assert na_segunda(10, 30).isoformat() in horarios


def test_disponibilidade_com_servico_inexistente_ou_inativo(
    client_publico: TestClient, session: Session, cenario: Cenario
):
    assert (
        client_publico.get(
            "/disponibilidade", params={"data": "2030-01-07", "servico_id": 999}
        ).status_code
        == 404
    )
    cenario.servico_30.ativo = False
    session.commit()
    assert (
        client_publico.get(
            "/disponibilidade", params={"data": "2030-01-07", "servico_id": cenario.servico_30.id}
        ).status_code
        == 422
    )


def test_marca_agendamento_e_devolve_confirmacao_com_codigo(
    client_publico: TestClient, cenario: Cenario, notificador: NotificadorFalso
):
    resposta = client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(10)))

    corpo = resposta.json()
    assert resposta.status_code == 201
    assert corpo["barbeiro"] == "João Barbeiro"
    assert corpo["servico"] == "Corte de cabelo"
    assert corpo["inicio"] == na_segunda(10).isoformat()
    assert corpo["fim"] == na_segunda(10, 30).isoformat()
    assert corpo["preco"] == "45.00"
    assert corpo["status"] == "agendado"
    assert len(corpo["codigo_cancelamento"]) >= 8
    assert len(notificador.enviados) == 1
    assert notificador.enviados[0].email == "maria@exemplo.com"


def test_conflito_retorna_409_e_nao_envia_confirmacao(
    client_publico: TestClient, cenario: Cenario, notificador: NotificadorFalso
):
    client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(10)))

    resposta = client_publico.post(
        "/agendamentos", json=_corpo(cenario, na_segunda(10), email="outro@exemplo.com")
    )

    assert resposta.status_code == 409
    assert len(notificador.enviados) == 1


@pytest.mark.parametrize(
    "extras",
    [
        {"email": "sem-arroba"},
        {"nome": "A"},
        {"telefone": "123"},
        {"inicio": "2030-01-07T10:00:00-03:00"},
    ],
    ids=["email", "nome-curto", "telefone-curto", "com-fuso"],
)
def test_dados_invalidos_retornam_422(client_publico: TestClient, cenario: Cenario, extras: dict):
    corpo = {**_corpo(cenario, na_segunda(10)), **extras}

    assert client_publico.post("/agendamentos", json=corpo).status_code == 422


def test_horario_fora_da_janela_e_no_passado_retornam_422(
    client_publico: TestClient, cenario: Cenario
):
    fora_da_janela = client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(18)))
    assert fora_da_janela.status_code == 422
    passado = datetime(2029, 12, 31, 10, 0)
    assert client_publico.post("/agendamentos", json=_corpo(cenario, passado)).status_code == 422


def test_barbeiro_ou_servico_inexistente_retorna_404(client_publico: TestClient, cenario: Cenario):
    corpo = _corpo(cenario, na_segunda(10), barbeiro_id=999)

    assert client_publico.post("/agendamentos", json=corpo).status_code == 404


def test_barbeiro_inativo_retorna_422(
    client_publico: TestClient, session: Session, cenario: Cenario
):
    cenario.barbeiro.ativo = False
    session.commit()

    resposta = client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(10)))

    assert resposta.status_code == 422


def _marcar(client_publico: TestClient, cenario: Cenario) -> dict:
    return client_publico.post("/agendamentos", json=_corpo(cenario, na_segunda(10))).json()


def test_cancela_com_codigo_e_horario_volta_a_ficar_livre(
    client_publico: TestClient, cenario: Cenario
):
    confirmacao = _marcar(client_publico, cenario)

    resposta = client_publico.post(
        f"/agendamentos/{confirmacao['id']}/cancelar",
        json={"codigo": confirmacao["codigo_cancelamento"]},
    )
    novo = client_publico.post(
        "/agendamentos", json=_corpo(cenario, na_segunda(10), email="outro@exemplo.com")
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"id": confirmacao["id"], "status": "cancelado"}
    assert novo.status_code == 201


def test_codigo_errado_e_agendamento_inexistente_tem_a_mesma_resposta(
    client_publico: TestClient, cenario: Cenario
):
    confirmacao = _marcar(client_publico, cenario)

    errado = client_publico.post(
        f"/agendamentos/{confirmacao['id']}/cancelar", json={"codigo": "errado"}
    )
    inexistente = client_publico.post("/agendamentos/999/cancelar", json={"codigo": "errado"})

    assert errado.status_code == inexistente.status_code == 404
    assert errado.json() == inexistente.json()


def test_cancelar_sem_corpo_retorna_422(client_publico: TestClient, cenario: Cenario):
    confirmacao = _marcar(client_publico, cenario)

    resposta = client_publico.post(f"/agendamentos/{confirmacao['id']}/cancelar", json={})

    assert resposta.status_code == 422


def test_nao_cancela_horario_que_ja_passou(
    client_publico: TestClient, app_publico: FastAPI, cenario: Cenario
):
    confirmacao = _marcar(client_publico, cenario)
    app_publico.dependency_overrides[get_agora] = lambda: datetime(2030, 1, 8)

    resposta = client_publico.post(
        f"/agendamentos/{confirmacao['id']}/cancelar",
        json={"codigo": confirmacao["codigo_cancelamento"]},
    )

    assert resposta.status_code == 422


def test_pagina_do_cliente_e_arquivos_estaticos(client_publico: TestClient):
    pagina = client_publico.get("/")

    assert pagina.status_code == 200
    assert pagina.headers["content-type"].startswith("text/html")
    assert "Marque seu horário" in pagina.text
    assert "javascript" in client_publico.get("/app.js").headers["content-type"]
    assert "javascript" in client_publico.get("/comum/util.js").headers["content-type"]
    assert "css" in client_publico.get("/comum/base.css").headers["content-type"]
    assert "Painel da Empresa" not in pagina.text


def test_cliente_novo_aparece_para_a_empresa(
    client_publico: TestClient, client: TestClient, cenario: Cenario, session: Session
):
    _marcar(client_publico, cenario)

    agendamentos = client.get("/agendamentos").json()["itens"]
    clientes = client.get("/clientes").json()

    assert len(agendamentos) == 1
    assert "maria@exemplo.com" in [c["email"] for c in clientes]
    assert "codigo_cancelamento" not in agendamentos[0]
    assert session.get(Barbeiro, cenario.barbeiro.id) is not None
