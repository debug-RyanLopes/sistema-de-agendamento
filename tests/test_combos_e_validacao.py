"""Combos (vários serviços num agendamento), nomes de até 120 caracteres e validações."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import Cenario
from tests.helpers import NotificadorFalso, na_segunda


def _corpo(cenario: Cenario, inicio, **extras) -> dict:
    return {
        "nome": "Maria Nova",
        "email": "maria@exemplo.com",
        "telefone": "(11) 91111-2222",
        "barbeiro_id": cenario.barbeiro.id,
        "inicio": inicio.isoformat(),
        **extras,
    }


def test_combo_soma_duracao_e_preco_e_descreve_os_servicos(
    client_publico: TestClient, client: TestClient, cenario: Cenario, notificador: NotificadorFalso
):
    corpo = _corpo(
        cenario, na_segunda(10), servico_ids=[cenario.servico_30.id, cenario.servico_60.id]
    )

    resposta = client_publico.post("/agendamentos", json=corpo)

    assert resposta.status_code == 201, resposta.text
    confirmacao = resposta.json()
    assert confirmacao["servico"] == "Corte de cabelo + Corte + barba"
    assert confirmacao["servicos"] == ["Corte de cabelo", "Corte + barba"]
    assert confirmacao["servico_ids"] == [cenario.servico_30.id, cenario.servico_60.id]
    assert confirmacao["duracao_minutos"] == 90
    assert confirmacao["fim"] == na_segunda(11, 30).isoformat()
    assert confirmacao["preco"] == "115.00"
    assert notificador.enviados[0].servico == "Corte de cabelo + Corte + barba"
    assert notificador.enviados[0].preco == 115
    detalhe = client.get(f"/agendamentos/{confirmacao['id']}").json()
    assert detalhe["servico_ids"] == confirmacao["servico_ids"]
    assert detalhe["servico_id"] == cenario.servico_30.id
    assert detalhe["preco"] == "115.00"


def test_combo_bloqueia_a_agenda_pela_duracao_total(client_publico: TestClient, cenario: Cenario):
    client_publico.post(
        "/agendamentos",
        json=_corpo(
            cenario, na_segunda(10), servico_ids=[cenario.servico_30.id, cenario.servico_60.id]
        ),
    )

    conflito = client_publico.post(
        "/agendamentos",
        json=_corpo(cenario, na_segunda(11), servico_id=cenario.servico_30.id, email="o@x.com"),
    )
    depois = client_publico.post(
        "/agendamentos",
        json=_corpo(
            cenario, na_segunda(11, 30), servico_id=cenario.servico_30.id, email="o@x.com"
        ),
    )

    assert conflito.status_code == 409
    assert depois.status_code == 201


def test_disponibilidade_para_combo_usa_a_duracao_somada(
    client_publico: TestClient, cenario: Cenario
):
    resposta = client_publico.get(
        "/disponibilidade",
        params={
            "data": "2030-01-07",
            "servico_ids": [cenario.servico_30.id, cenario.servico_60.id],
        },
    )

    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["duracao_minutos"] == 90
    assert corpo["preco"] == "115.00"
    assert corpo["servico_ids"] == [cenario.servico_30.id, cenario.servico_60.id]
    horarios = [h[11:16] for h in corpo["barbeiros"][0]["horarios"]]
    assert horarios[:3] == ["09:00", "10:30", "12:00"]
    assert horarios[-1] == "16:30"  # 16:30-18:00 é o último que cabe


def test_horarios_livres_da_empresa_aceitam_combo(client: TestClient, cenario_api: dict[str, int]):
    resposta = client.get(
        f"/barbeiros/{cenario_api['barbeiro_id']}/horarios-livres",
        params={
            "data": "2030-01-07",
            "servico_ids": [cenario_api["servico_30_id"], cenario_api["servico_60_id"]],
        },
    )
    sem_servico = client.get(
        f"/barbeiros/{cenario_api['barbeiro_id']}/horarios-livres", params={"data": "2030-01-07"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["duracao_minutos"] == 90
    assert sem_servico.status_code == 422


def test_disponibilidade_sem_servico_retorna_422(client_publico: TestClient):
    assert client_publico.get("/disponibilidade", params={"data": "2030-01-07"}).status_code == 422


@pytest.mark.parametrize(
    "servicos",
    [
        {"servico_ids": []},
        {"servico_ids": [1, 2, 3, 4, 5, 6]},
        {},
    ],
)
def test_agendamento_precisa_de_um_a_cinco_servicos(
    client_publico: TestClient, cenario: Cenario, servicos: dict
):
    resposta = client_publico.post(
        "/agendamentos", json=_corpo(cenario, na_segunda(10), **servicos)
    )

    assert resposta.status_code == 422


def test_servico_repetido_no_combo_conta_uma_vez(client_publico: TestClient, cenario: Cenario):
    resposta = client_publico.post(
        "/agendamentos",
        json=_corpo(
            cenario, na_segunda(10), servico_ids=[cenario.servico_30.id, cenario.servico_30.id]
        ),
    )

    assert resposta.status_code == 201
    assert resposta.json()["duracao_minutos"] == 30
    assert resposta.json()["servico_ids"] == [cenario.servico_30.id]


def test_servico_inativo_ou_inexistente_no_combo(
    client_publico: TestClient, session: Session, cenario: Cenario
):
    cenario.servico_60.ativo = False
    session.commit()

    inativo = client_publico.post(
        "/agendamentos",
        json=_corpo(
            cenario, na_segunda(10), servico_ids=[cenario.servico_30.id, cenario.servico_60.id]
        ),
    )
    inexistente = client_publico.post(
        "/agendamentos",
        json=_corpo(cenario, na_segunda(10), servico_ids=[cenario.servico_30.id, 999]),
    )

    assert inativo.status_code == 422
    assert inexistente.status_code == 404


def test_empresa_marca_combo_e_remarca_mantendo_a_duracao(
    client: TestClient, cenario_api: dict[str, int]
):
    criado = client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_ids": [cenario_api["servico_30_id"], cenario_api["servico_60_id"]],
            "inicio": na_segunda(10).isoformat(),
        },
    )
    assert criado.status_code == 201, criado.text

    remarcado = client.post(
        f"/agendamentos/{criado.json()['id']}/reagendar",
        json={"inicio": na_segunda(14).isoformat()},
    )
    csv = client.get("/relatorios/agendamentos.csv").text
    impacto = client.get(f"/barbeiros/{cenario_api['barbeiro_id']}/impacto-desativacao").json()

    assert remarcado.json()["fim"] == na_segunda(15, 30).isoformat()
    assert remarcado.json()["servico_ids"] == [
        cenario_api["servico_30_id"],
        cenario_api["servico_60_id"],
    ]
    assert "Corte de cabelo + Corte + barba;115,00" in csv
    assert impacto["agendamentos_futuros"][0]["servico"] == "Corte de cabelo + Corte + barba"
    assert impacto["valor_futuro"] == "115.00"


def test_meus_agendamentos_mostram_o_combo(
    client_publico: TestClient, cenario: Cenario, notificador: NotificadorFalso
):
    client_publico.post(
        "/agendamentos",
        json=_corpo(
            cenario, na_segunda(10), servico_ids=[cenario.servico_30.id, cenario.servico_60.id]
        ),
    )
    client_publico.post("/meus-agendamentos/solicitar", json={"email": "maria@exemplo.com"})
    token = notificador.links[-1][2].split("token=")[1]

    meus = client_publico.get("/meus-agendamentos", params={"token": token}).json()

    assert meus["agendamentos"][0]["servico"] == "Corte de cabelo + Corte + barba"
    assert meus["agendamentos"][0]["servico_ids"] == [cenario.servico_30.id, cenario.servico_60.id]


def test_relatorio_usa_o_preco_do_combo(client: TestClient, cenario_api: dict[str, int]):
    client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_ids": [cenario_api["servico_30_id"], cenario_api["servico_60_id"]],
            "inicio": na_segunda(10).isoformat(),
        },
    )

    resumo = client.get(
        "/relatorios/resumo", params={"desde": "2030-01-07", "ate": "2030-01-07"}
    ).json()

    assert resumo["receita"] == "115.00"
    assert resumo["barbeiros"][0]["minutos_ocupados"] == 90


# --- nome com 120 caracteres e validações ---------------------------------------------------


@pytest.mark.parametrize("rota", ["/clientes", "/barbeiros", "/servicos", "/produtos"])
def test_nome_aceita_ate_120_caracteres(client: TestClient, rota: str):
    base = {
        "/clientes": {"email": "n@x.com", "telefone": "92991112222"},
        "/barbeiros": {"email": "b@x.com"},
        "/servicos": {"duracao_minutos": 30, "preco": "10.00"},
        "/produtos": {"preco": "10.00", "estoque": 1},
    }[rota]

    aceito = client.post(rota, json={**base, "nome": "N" * 120})
    recusado = client.post(rota, json={**base, "nome": "N" * 121})

    assert aceito.status_code == 201
    assert recusado.status_code == 422


def test_cliente_publico_tem_nome_limitado_a_120(client_publico: TestClient, cenario: Cenario):
    longo = client_publico.post(
        "/agendamentos",
        json=_corpo(cenario, na_segunda(10), servico_id=cenario.servico_30.id, nome="N" * 121),
    )
    exato = client_publico.post(
        "/agendamentos",
        json=_corpo(cenario, na_segunda(10), servico_id=cenario.servico_30.id, nome="N" * 120),
    )

    assert longo.status_code == 422
    assert exato.status_code == 201


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("email", "sem-arroba", "e-mail inválido"),
        ("email", "a@b", "e-mail inválido"),
        ("telefone", "123", "DDD"),
        ("telefone", "(92) 81234-5678", "9 depois do DDD"),
        ("telefone", "92 1234-5678", "2, 3, 4 ou 5"),
        ("telefone", "abc", "só números"),
    ],
)
def test_email_e_telefone_invalidos_explicam_o_motivo(
    client_publico: TestClient, cenario: Cenario, campo: str, valor: str, trecho: str
):
    resposta = client_publico.post(
        "/agendamentos",
        json=_corpo(cenario, na_segunda(10), servico_id=cenario.servico_30.id, **{campo: valor}),
    )

    assert resposta.status_code == 422
    assert trecho in resposta.text


def test_telefone_com_mascara_e_email_com_maiusculas_sao_normalizados(
    client_publico: TestClient, client: TestClient, cenario: Cenario
):
    resposta = client_publico.post(
        "/agendamentos",
        json=_corpo(
            cenario,
            na_segunda(10),
            servico_id=cenario.servico_30.id,
            email=" Maria@Exemplo.COM ",
            telefone="(11) 91111-2222",
        ),
    )

    assert resposta.status_code == 201
    cliente = client.get("/clientes", params={"busca": "maria"}).json()[0]
    assert cliente["email"] == "maria@exemplo.com"
    assert cliente["telefone"] == "11911112222"
