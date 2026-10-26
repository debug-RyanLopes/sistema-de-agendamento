"""Vendas com baixa de estoque, relatório de ocupação/receita, CSV e busca nos cadastros."""

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.helpers import AGORA_FIXO, na_segunda


def _produto(client: TestClient, nome: str, preco: str, estoque: int) -> dict:
    return client.post("/produtos", json={"nome": nome, "preco": preco, "estoque": estoque}).json()


def _agendar(client: TestClient, cenario_api: dict[str, int], inicio) -> dict:
    resposta = client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": inicio.isoformat(),
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _no_passado(client: TestClient, cenario_api: dict, session, status: str) -> int:
    from app.models import Agendamento, StatusAgendamento

    inicio = AGORA_FIXO.replace(hour=7)
    agendamento = Agendamento(
        cliente_id=cenario_api["cliente_id"],
        barbeiro_id=cenario_api["barbeiro_id"],
        servico_id=cenario_api["servico_30_id"],
        inicio=inicio,
        fim=inicio.replace(minute=30),
        status=StatusAgendamento.AGENDADO,
    )
    session.add(agendamento)
    session.commit()
    if status != "agendado":
        assert (
            client.patch(
                f"/agendamentos/{agendamento.id}/status", json={"status": status}
            ).status_code
            == 200
        )
    return agendamento.id


# --- vendas ---------------------------------------------------------------------------------


def test_venda_baixa_o_estoque_e_soma_em_decimal(client: TestClient):
    pomada = _produto(client, "Pomada", "35.90", 10)
    oleo = _produto(client, "Óleo", "0.10", 5)

    venda = client.post(
        "/vendas",
        json={
            "itens": [
                {"produto_id": pomada["id"], "quantidade": 2},
                {"produto_id": oleo["id"], "quantidade": 3},
            ],
            "observacao": "pago no pix",
        },
    )

    assert venda.status_code == 201
    corpo = venda.json()
    assert corpo["total"] == "72.10"
    assert corpo["criado_em"] == AGORA_FIXO.isoformat()
    assert [item["preco_unitario"] for item in corpo["itens"]] == ["35.90", "0.10"]
    assert client.get(f"/produtos/{pomada['id']}").json()["estoque"] == 8
    assert client.get(f"/produtos/{oleo['id']}").json()["estoque"] == 2
    lista = client.get("/vendas").json()
    assert [v["id"] for v in lista] == [corpo["id"]]
    assert lista[0]["observacao"] == "pago no pix"


def test_estoque_insuficiente_em_um_item_cancela_a_venda_inteira(client: TestClient):
    pomada = _produto(client, "Pomada", "35.90", 10)
    oleo = _produto(client, "Óleo", "42.00", 1)

    venda = client.post(
        "/vendas",
        json={
            "itens": [
                {"produto_id": pomada["id"], "quantidade": 2},
                {"produto_id": oleo["id"], "quantidade": 2},
            ]
        },
    )

    assert venda.status_code == 409
    assert "Óleo" in venda.json()["detail"]
    assert client.get(f"/produtos/{pomada['id']}").json()["estoque"] == 10
    assert client.get("/vendas").json() == []


def test_venda_de_produto_inativo_ou_inexistente(client: TestClient):
    pomada = _produto(client, "Pomada", "35.90", 10)
    client.patch(f"/produtos/{pomada['id']}/ativo", json={"ativo": False})

    inativo = client.post(
        "/vendas", json={"itens": [{"produto_id": pomada["id"], "quantidade": 1}]}
    )
    inexistente = client.post("/vendas", json={"itens": [{"produto_id": 999, "quantidade": 1}]})
    vazia = client.post("/vendas", json={"itens": []})

    assert inativo.status_code == 422
    assert inexistente.status_code == 404
    assert vazia.status_code == 422


# --- relatórios ------------------------------------------------------------------------------


def test_resumo_calcula_ocupacao_receita_e_status(
    client: TestClient, cenario_api: dict[str, int], session
):
    _no_passado(client, cenario_api, session, "concluido")
    _no_passado(client, cenario_api, session, "nao_compareceu")
    futuro = _agendar(client, cenario_api, na_segunda(10))
    cancelado = _agendar(client, cenario_api, na_segunda(11))
    client.delete(f"/agendamentos/{cancelado['id']}")
    pomada = _produto(client, "Pomada", "10.00", 5)
    client.post("/vendas", json={"itens": [{"produto_id": pomada["id"], "quantidade": 2}]})

    resposta = client.get(
        "/relatorios/resumo", params={"desde": "2030-01-01", "ate": "2030-01-07"}
    )

    assert resposta.status_code == 200
    resumo = resposta.json()
    assert resumo["total_agendamentos"] == 4
    assert resumo["receita"] == "90.00"  # concluído + agendado futuro; falta e cancelado não
    assert resumo["receita_produtos"] == "20.00"
    [barbeiro] = resumo["barbeiros"]
    assert (
        barbeiro["agendados"],
        barbeiro["concluidos"],
        barbeiro["faltas"],
        barbeiro["cancelados"],
    ) == (1, 1, 1, 1)
    assert barbeiro["minutos_ocupados"] == 60
    assert barbeiro["minutos_disponiveis"] == 9 * 60  # só a segunda (07/01) tem janela 9-18
    assert barbeiro["ocupacao"] == round(60 / 540, 3)
    assert futuro["id"]


def test_resumo_recusa_periodo_invertido_ou_longo(client: TestClient):
    invertido = client.get(
        "/relatorios/resumo", params={"desde": "2030-02-01", "ate": "2030-01-01"}
    )
    longo = client.get("/relatorios/resumo", params={"desde": "2030-01-01", "ate": "2030-06-01"})

    assert invertido.status_code == 422
    assert longo.status_code == 422


def test_csv_exporta_com_nomes_e_respeita_filtros(client: TestClient, cenario_api: dict[str, int]):
    _agendar(client, cenario_api, na_segunda(10))
    cancelado = _agendar(client, cenario_api, na_segunda(11))
    client.delete(f"/agendamentos/{cancelado['id']}")

    tudo = client.get("/relatorios/agendamentos.csv")
    so_cancelados = client.get("/relatorios/agendamentos.csv", params={"status": "cancelado"})

    assert tudo.status_code == 200
    assert tudo.headers["content-type"].startswith("text/csv")
    assert "agendamentos.csv" in tudo.headers["content-disposition"]
    linhas = tudo.text.lstrip("﻿").splitlines()
    assert linhas[0] == "id;inicio;fim;cliente;barbeiro;servico;preco;status;origem"
    assert len(linhas) == 3
    assert "Carlos Silva;João Barbeiro;Corte de cabelo;45,00;agendado;empresa" in linhas[1]
    assert len(so_cancelados.text.splitlines()) == 2


# --- cadastros: busca e paginação -----------------------------------------------------------


def test_lista_de_cadastros_busca_pagina_e_informa_o_total(client: TestClient):
    for i in range(6):
        client.post(
            "/clientes",
            json={
                "nome": f"Cliente {i}",
                "email": f"c{i}@exemplo.com",
                "telefone": f"9299111000{i}",
            },
        )
    client.post(
        "/clientes",
        json={"nome": "Zé Procurado", "email": "ze@exemplo.com", "telefone": "92988887777"},
    )

    pagina = client.get("/clientes", params={"limite": 4, "deslocamento": 4})
    por_nome = client.get("/clientes", params={"busca": "procurado"})
    por_email = client.get("/clientes", params={"busca": "C3@EXEMPLO"})
    por_telefone = client.get("/clientes", params={"busca": "(92) 98888-7777"})
    recentes = client.get("/clientes", params={"ordem": "recentes", "limite": 1})

    assert pagina.headers["x-total-count"] == "7"
    assert len(pagina.json()) == 3
    assert [c["nome"] for c in por_nome.json()] == ["Zé Procurado"]
    assert [c["email"] for c in por_email.json()] == ["c3@exemplo.com"]
    assert [c["nome"] for c in por_telefone.json()] == ["Zé Procurado"]
    assert por_telefone.headers["x-total-count"] == "1"
    assert recentes.json()[0]["nome"] == "Zé Procurado"
    assert client.get("/clientes", params={"ordem": "aleatoria"}).status_code == 422


def test_dono_apaga_dados_do_cliente_mantendo_o_historico(
    client: TestClient, cenario_api: dict[str, int]
):
    futuro = _agendar(client, cenario_api, na_segunda(10))

    com_futuro = client.post(f"/clientes/{cenario_api['cliente_id']}/anonimizar")
    client.delete(f"/agendamentos/{futuro['id']}")
    apagado = client.post(f"/clientes/{cenario_api['cliente_id']}/anonimizar")

    assert com_futuro.status_code == 409
    assert apagado.status_code == 200
    assert apagado.json()["nome"] == "Cliente removido"
    assert apagado.json()["email"].endswith("@anonimo.invalid")
    assert apagado.json()["ativo"] is False
    assert (
        client.get(f"/agendamentos/{futuro['id']}").json()["cliente_id"]
        == cenario_api["cliente_id"]
    )
    assert client.post("/clientes/999/anonimizar").status_code == 404
    assert isinstance(Decimal("0"), Decimal)
