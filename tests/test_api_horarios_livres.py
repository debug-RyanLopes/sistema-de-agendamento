from datetime import datetime

from fastapi.testclient import TestClient

from tests.helpers import na_segunda


def _consultar(client: TestClient, cenario_api: dict[str, int], data: str = "2030-01-07"):
    return client.get(
        f"/barbeiros/{cenario_api['barbeiro_id']}/horarios-livres",
        params={"data": data, "servico_id": cenario_api["servico_30_id"]},
    )


def _horarios(resposta) -> list[datetime]:
    return [datetime.fromisoformat(item) for item in resposta.json()["horarios"]]


def test_at008_lista_exclui_slots_que_sobrepoem_agendamento(
    client: TestClient, cenario_api: dict[str, int]
):
    client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": na_segunda(10).isoformat(),
        },
    )

    resposta = _consultar(client, cenario_api)
    horarios = _horarios(resposta)

    assert resposta.status_code == 200
    assert na_segunda(9, 30) in horarios
    assert na_segunda(10, 30) in horarios
    for ocupado in (na_segunda(9, 45), na_segunda(10), na_segunda(10, 15)):
        assert ocupado not in horarios


def test_dia_sem_disponibilidade_retorna_lista_vazia(
    client: TestClient, cenario_api: dict[str, int]
):
    resposta = _consultar(client, cenario_api, data="2030-01-06")

    assert resposta.status_code == 200
    assert resposta.json()["horarios"] == []


def test_barbeiro_ou_servico_inexistente_retorna_404(
    client: TestClient, cenario_api: dict[str, int]
):
    sem_barbeiro = client.get(
        "/barbeiros/999/horarios-livres",
        params={"data": "2030-01-07", "servico_id": cenario_api["servico_30_id"]},
    )
    sem_servico = client.get(
        f"/barbeiros/{cenario_api['barbeiro_id']}/horarios-livres",
        params={"data": "2030-01-07", "servico_id": 999},
    )

    assert sem_barbeiro.status_code == 404
    assert sem_servico.status_code == 404


def test_parametros_ausentes_ou_invalidos_retornam_422(
    client: TestClient, cenario_api: dict[str, int]
):
    base = f"/barbeiros/{cenario_api['barbeiro_id']}/horarios-livres"

    assert client.get(base).status_code == 422
    assert client.get(base, params={"data": "ontem", "servico_id": 1}).status_code == 422
