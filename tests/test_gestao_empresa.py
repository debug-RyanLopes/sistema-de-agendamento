import pytest
from fastapi.testclient import TestClient

from tests.helpers import na_segunda

CLIENTE = {"nome": "Carlos Silva", "email": "carlos@exemplo.com", "telefone": "11987654321"}
BARBEIRO = {"nome": "João Barbeiro", "email": "joao@barbearia.com"}
SERVICO = {"nome": "Corte de cabelo", "duracao_minutos": 30, "preco": "45.00"}
PRODUTO = {"nome": "Pomada modeladora", "preco": 35.9, "estoque": 12}

CADASTROS = [
    (
        "/clientes",
        CLIENTE,
        {"nome": "Carlos Souza", "email": "novo@exemplo.com", "telefone": "1122223333"},
    ),
    ("/barbeiros", BARBEIRO, {"nome": "Pedro Navalha", "email": "pedro@barbearia.com"}),
    ("/servicos", SERVICO, {"nome": "Barba", "duracao_minutos": 20, "preco": "30.00"}),
    ("/produtos", PRODUTO, {"nome": "Óleo para barba", "preco": "42.00", "estoque": 3}),
]


@pytest.mark.parametrize(("rota", "original", "novo"), CADASTROS)
def test_edita_cadastro(client: TestClient, rota: str, original: dict, novo: dict):
    identificador = client.post(rota, json=original).json()["id"]

    resposta = client.put(f"{rota}/{identificador}", json=novo)

    assert resposta.status_code == 200
    for campo, valor in novo.items():
        assert resposta.json()[campo] == valor
    assert client.get(f"{rota}/{identificador}").json()["nome"] == novo["nome"]


@pytest.mark.parametrize(("rota", "original", "novo"), CADASTROS)
def test_edicao_inexistente_retorna_404_e_invalida_retorna_422(
    client: TestClient, rota: str, original: dict, novo: dict
):
    identificador = client.post(rota, json=original).json()["id"]

    assert client.put(f"{rota}/999", json=novo).status_code == 404
    assert client.put(f"{rota}/{identificador}", json={"nome": "X"}).status_code == 422


@pytest.mark.parametrize(("rota", "original", "novo"), CADASTROS)
def test_desativa_e_reativa_sem_perder_o_registro(
    client: TestClient, rota: str, original: dict, novo: dict
):
    identificador = client.post(rota, json=original).json()["id"]

    desativado = client.patch(f"{rota}/{identificador}/ativo", json={"ativo": False})
    padrao = client.get(rota).json()
    com_inativos = client.get(rota, params={"incluir_inativos": True}).json()
    reativado = client.patch(f"{rota}/{identificador}/ativo", json={"ativo": True})

    assert desativado.json()["ativo"] is False
    assert padrao == []
    assert [item["id"] for item in com_inativos] == [identificador]
    assert reativado.json()["ativo"] is True
    assert len(client.get(rota).json()) == 1


@pytest.mark.parametrize("rota", ["/clientes", "/barbeiros", "/servicos", "/produtos"])
def test_ativar_inexistente_retorna_404_e_corpo_invalido_retorna_422(
    client: TestClient, rota: str
):
    assert client.patch(f"{rota}/999/ativo", json={"ativo": False}).status_code == 404
    assert client.patch(f"{rota}/1/ativo", json={}).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {**PRODUTO, "preco": -1},
        {**PRODUTO, "estoque": -1},
        {**PRODUTO, "nome": "P"},
        {"nome": "Pomada"},
    ],
)
def test_produto_invalido_retorna_422(client: TestClient, payload: dict):
    assert client.post("/produtos", json=payload).status_code == 422


def test_produto_guarda_estoque_e_preco(client: TestClient):
    criado = client.post("/produtos", json=PRODUTO).json()

    assert criado["estoque"] == 12
    assert criado["preco"] == "35.90"
    assert criado["ativo"] is True


def test_remove_janela_de_disponibilidade(client: TestClient, cenario_api: dict[str, int]):
    barbeiro_id = cenario_api["barbeiro_id"]
    janela_id = client.get(f"/barbeiros/{barbeiro_id}/disponibilidades").json()[0]["id"]

    resposta = client.delete(f"/barbeiros/{barbeiro_id}/disponibilidades/{janela_id}")

    assert resposta.status_code == 204
    assert client.get(f"/barbeiros/{barbeiro_id}/disponibilidades").json() == []


def test_nao_remove_janela_de_outro_barbeiro_nem_inexistente(
    client: TestClient, cenario_api: dict[str, int]
):
    outro = client.post("/barbeiros", json={**BARBEIRO, "email": "outro@barbearia.com"}).json()
    janela_id = client.get(f"/barbeiros/{cenario_api['barbeiro_id']}/disponibilidades").json()[0][
        "id"
    ]

    de_outro = client.delete(f"/barbeiros/{outro['id']}/disponibilidades/{janela_id}")
    assert de_outro.status_code == 404
    assert client.delete(f"/barbeiros/{outro['id']}/disponibilidades/999").status_code == 404
    assert client.delete(f"/barbeiros/999/disponibilidades/{janela_id}").status_code == 404


def _agendar(client: TestClient, ids: dict[str, int]):
    return client.post(
        "/agendamentos",
        json={
            "cliente_id": ids["cliente_id"],
            "barbeiro_id": ids["barbeiro_id"],
            "servico_id": ids["servico_30_id"],
            "inicio": na_segunda(10).isoformat(),
        },
    )


@pytest.mark.parametrize(
    ("rota", "chave"),
    [("/clientes", "cliente_id"), ("/barbeiros", "barbeiro_id"), ("/servicos", "servico_30_id")],
)
def test_cadastro_inativo_nao_recebe_novo_agendamento(
    client: TestClient, cenario_api: dict[str, int], rota: str, chave: str
):
    client.patch(f"{rota}/{cenario_api[chave]}/ativo", json={"ativo": False})

    assert _agendar(client, cenario_api).status_code == 422


def test_historico_continua_visivel_depois_de_desativar(
    client: TestClient, cenario_api: dict[str, int]
):
    _agendar(client, cenario_api)

    client.patch(f"/barbeiros/{cenario_api['barbeiro_id']}/ativo", json={"ativo": False})

    assert client.get("/agendamentos").json()["total"] == 1


def test_filtra_agendamentos_por_status(client: TestClient, cenario_api: dict[str, int]):
    agendamento = _agendar(client, cenario_api).json()
    client.delete(f"/agendamentos/{agendamento['id']}")

    cancelados = client.get("/agendamentos", params={"status": "cancelado"}).json()["itens"]
    agendados = client.get("/agendamentos", params={"status": "agendado"}).json()["itens"]

    assert [item["id"] for item in cancelados] == [agendamento["id"]]
    assert agendados == []
    assert client.get("/agendamentos", params={"status": "inexistente"}).status_code == 422


def test_empresa_cancela_agendamento_feito_pelo_cliente(
    client: TestClient, client_publico: TestClient, cenario_api: dict[str, int]
):
    corpo = {
        "nome": "Maria Nova",
        "email": "maria@exemplo.com",
        "telefone": "11911112222",
        "barbeiro_id": cenario_api["barbeiro_id"],
        "servico_id": cenario_api["servico_30_id"],
        "inicio": na_segunda(10).isoformat(),
    }
    confirmacao = client_publico.post("/agendamentos", json=corpo).json()

    cancelado = client.delete(f"/agendamentos/{confirmacao['id']}")
    tentativa = client_publico.post(
        f"/agendamentos/{confirmacao['id']}/cancelar",
        json={"codigo": confirmacao["codigo_cancelamento"]},
    )

    assert cancelado.json()["status"] == "cancelado"
    assert tentativa.status_code == 200
