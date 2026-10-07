import pytest
from fastapi.testclient import TestClient

CLIENTE = {"nome": "Carlos Silva", "email": "  Carlos@Exemplo.com ", "telefone": "11987654321"}
BARBEIRO = {"nome": "João Barbeiro", "email": "joao@barbearia.com"}
SERVICO = {"nome": "Corte de cabelo", "duracao_minutos": 30, "preco": 45.0}


@pytest.mark.parametrize(
    ("rota", "payload"),
    [("/clientes", CLIENTE), ("/barbeiros", BARBEIRO), ("/servicos", SERVICO)],
)
def test_cria_lista_e_obtem_cadastro(client: TestClient, rota: str, payload: dict):
    criado = client.post(rota, json=payload)

    assert criado.status_code == 201
    identificador = criado.json()["id"]
    assert [item["id"] for item in client.get(rota).json()] == [identificador]
    assert client.get(f"{rota}/{identificador}").json()["id"] == identificador


def test_email_e_normalizado(client: TestClient):
    resposta = client.post("/clientes", json=CLIENTE)

    assert resposta.json()["email"] == "carlos@exemplo.com"


@pytest.mark.parametrize("rota", ["/clientes", "/barbeiros", "/servicos"])
def test_cadastro_inexistente_retorna_404(client: TestClient, rota: str):
    resposta = client.get(f"{rota}/999")

    assert resposta.status_code == 404
    assert "detail" in resposta.json()


@pytest.mark.parametrize(
    ("rota", "payload"),
    [
        ("/clientes", {**CLIENTE, "email": "sem-arroba"}),
        ("/clientes", {**CLIENTE, "telefone": "123"}),
        ("/clientes", {"nome": "Carlos Silva"}),
        ("/barbeiros", {**BARBEIRO, "email": "invalido"}),
        ("/servicos", {**SERVICO, "duracao_minutos": 0}),
        ("/servicos", {**SERVICO, "preco": -1}),
    ],
)
def test_cadastro_invalido_retorna_422(client: TestClient, rota: str, payload: dict):
    assert client.post(rota, json=payload).status_code == 422


def test_cadastra_e_lista_disponibilidade(client: TestClient):
    barbeiro_id = client.post("/barbeiros", json=BARBEIRO).json()["id"]

    criada = client.post(
        f"/barbeiros/{barbeiro_id}/disponibilidades",
        json={"dia_semana": 0, "hora_inicio": "09:00:00", "hora_fim": "18:00:00"},
    )
    listada = client.get(f"/barbeiros/{barbeiro_id}/disponibilidades")

    assert criada.status_code == 201
    assert listada.json()[0]["hora_inicio"] == "09:00:00"


@pytest.mark.parametrize(
    "janela",
    [
        {"dia_semana": 7, "hora_inicio": "09:00:00", "hora_fim": "18:00:00"},
        {"dia_semana": 0, "hora_inicio": "18:00:00", "hora_fim": "09:00:00"},
        {"dia_semana": 0, "hora_inicio": "09:00:00", "hora_fim": "09:00:00"},
    ],
    ids=["dia-invalido", "inicio-depois-do-fim", "inicio-igual-ao-fim"],
)
def test_disponibilidade_invalida_retorna_422(client: TestClient, janela: dict):
    barbeiro_id = client.post("/barbeiros", json=BARBEIRO).json()["id"]

    resposta = client.post(f"/barbeiros/{barbeiro_id}/disponibilidades", json=janela)

    assert resposta.status_code == 422


def test_disponibilidade_de_barbeiro_inexistente_retorna_404(client: TestClient):
    janela = {"dia_semana": 0, "hora_inicio": "09:00:00", "hora_fim": "18:00:00"}

    assert client.post("/barbeiros/999/disponibilidades", json=janela).status_code == 404
    assert client.get("/barbeiros/999/disponibilidades").status_code == 404
