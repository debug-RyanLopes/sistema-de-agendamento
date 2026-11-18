"""Janelas que se encostam valem como uma só; bloqueios tiram horários sem mexer na semana."""

import pytest
from app.config import Config
from app.services import disponibilidade_service
from fastapi.testclient import TestClient

from tests.helpers import SEGUNDA, na_segunda

DIA = SEGUNDA.date().isoformat()


def _janela(client: TestClient, barbeiro_id: int, inicio: str, fim: str, dia: int = 0):
    return client.post(
        f"/barbeiros/{barbeiro_id}/disponibilidades",
        json={"dia_semana": dia, "hora_inicio": inicio, "hora_fim": fim},
    )


def _livres(client: TestClient, cenario_api: dict[str, int], servico="servico_30_id") -> list[str]:
    resposta = client.get(
        f"/barbeiros/{cenario_api['barbeiro_id']}/horarios-livres",
        params={"data": DIA, "servico_id": cenario_api[servico]},
    )
    return [h[11:16] for h in resposta.json()["horarios"]]


def _marcar(client: TestClient, cenario_api: dict[str, int], inicio):
    return client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": inicio.isoformat(),
        },
    )


@pytest.fixture
def barbeiro_com_duas_janelas(client: TestClient, cenario_api: dict[str, int]) -> dict[str, int]:
    """Troca a janela única 9-18 por 9-12 e 12-18."""
    janelas = client.get(f"/barbeiros/{cenario_api['barbeiro_id']}/disponibilidades").json()
    for janela in janelas:
        client.delete(f"/barbeiros/{cenario_api['barbeiro_id']}/disponibilidades/{janela['id']}")
    _janela(client, cenario_api["barbeiro_id"], "09:00:00", "12:00:00")
    _janela(client, cenario_api["barbeiro_id"], "12:00:00", "18:00:00")
    return cenario_api


def test_janelas_adjacentes_oferecem_o_horario_na_fronteira(
    client: TestClient, barbeiro_com_duas_janelas: dict[str, int]
):
    livres = _livres(client, barbeiro_com_duas_janelas)

    assert "11:30" in livres and "12:00" in livres  # 11:30-12:00 e 12:00-12:30 cruzam a fronteira
    assert _marcar(client, barbeiro_com_duas_janelas, na_segunda(11, 45)).status_code == 201


def test_janelas_separadas_continuam_separadas(client: TestClient, cenario_api: dict[str, int]):
    janelas = client.get(f"/barbeiros/{cenario_api['barbeiro_id']}/disponibilidades").json()
    for janela in janelas:
        client.delete(f"/barbeiros/{cenario_api['barbeiro_id']}/disponibilidades/{janela['id']}")
    _janela(client, cenario_api["barbeiro_id"], "09:00:00", "12:00:00")
    _janela(client, cenario_api["barbeiro_id"], "13:00:00", "18:00:00")

    livres = _livres(client, cenario_api)

    assert "12:00" not in livres
    assert "11:30" in livres
    assert _marcar(client, cenario_api, na_segunda(11, 45)).status_code == 422


def test_fundir_junta_sobrepostos_e_encostados():
    from datetime import datetime

    def d(hora, minuto=0):
        return datetime(2030, 1, 7, hora, minuto)

    fundidos = disponibilidade_service._fundir(
        [(d(13), d(18)), (d(9), d(11)), (d(11), d(12)), (d(10), d(11, 30)), (d(19), d(20))]
    )

    assert fundidos == [(d(9), d(12)), (d(13), d(18)), (d(19), d(20))]


def test_bloqueio_do_dia_inteiro_tira_o_barbeiro_da_agenda(
    client: TestClient, client_publico: TestClient, cenario_api: dict[str, int]
):
    bloqueio = client.post(
        "/bloqueios",
        json={"barbeiro_id": cenario_api["barbeiro_id"], "data": DIA, "motivo": "Folga"},
    )

    assert bloqueio.status_code == 201
    assert _livres(client, cenario_api) == []
    publico = client_publico.get(
        "/disponibilidade", params={"data": DIA, "servico_id": cenario_api["servico_30_id"]}
    ).json()
    assert publico["barbeiros"] == []
    assert _marcar(client, cenario_api, na_segunda(10)).status_code == 422


def test_bloqueio_parcial_remove_so_o_trecho(client: TestClient, cenario_api: dict[str, int]):
    client.post(
        "/bloqueios",
        json={
            "barbeiro_id": cenario_api["barbeiro_id"],
            "data": DIA,
            "hora_inicio": "12:00:00",
            "hora_fim": "13:00:00",
            "motivo": "Almoço",
        },
    )

    livres = _livres(client, cenario_api)

    assert "11:30" in livres
    assert "11:45" not in livres  # 11:45-12:15 invade o almoço
    assert "12:00" not in livres
    assert "13:00" in livres
    assert _marcar(client, cenario_api, na_segunda(12, 30)).status_code == 422
    assert _marcar(client, cenario_api, na_segunda(13)).status_code == 201


def test_bloqueio_sem_barbeiro_fecha_a_barbearia_toda(client: TestClient, cenario_api: dict):
    outro = client.post("/barbeiros", json={"nome": "Pedro", "email": "pedro@b.com"}).json()
    _janela(client, outro["id"], "09:00:00", "18:00:00")

    client.post("/bloqueios", json={"data": DIA, "motivo": "Feriado"})

    assert _livres(client, cenario_api) == []
    outro_livres = client.get(
        f"/barbeiros/{outro['id']}/horarios-livres",
        params={"data": DIA, "servico_id": cenario_api["servico_30_id"]},
    ).json()["horarios"]
    assert outro_livres == []


def test_bloqueio_em_outro_dia_nao_interfere(client: TestClient, cenario_api: dict[str, int]):
    client.post("/bloqueios", json={"data": "2030-01-08"})

    assert "10:00" in _livres(client, cenario_api)


def test_lista_e_remove_bloqueios(client: TestClient, cenario_api: dict[str, int]):
    criado = client.post("/bloqueios", json={"data": DIA, "motivo": "Feriado"}).json()
    client.post("/bloqueios", json={"data": "2029-12-25"})

    todos = client.get("/bloqueios").json()
    futuros = client.get("/bloqueios", params={"desde": "2030-01-01"}).json()
    do_barbeiro = client.get("/bloqueios", params={"barbeiro_id": 999}).json()
    removido = client.delete(f"/bloqueios/{criado['id']}")

    assert len(todos) == 2
    assert [item["id"] for item in futuros] == [criado["id"]]
    assert len(do_barbeiro) == 2  # bloqueios gerais valem para qualquer barbeiro
    assert removido.status_code == 204
    assert client.delete(f"/bloqueios/{criado['id']}").status_code == 404
    assert "10:00" in _livres(client, cenario_api)


@pytest.mark.parametrize(
    "corpo",
    [
        {"data": DIA, "hora_inicio": "12:00:00"},
        {"data": DIA, "hora_inicio": "13:00:00", "hora_fim": "12:00:00"},
        {"data": "nao-e-data"},
        {},
    ],
)
def test_bloqueio_invalido_retorna_422(client: TestClient, corpo: dict):
    assert client.post("/bloqueios", json=corpo).status_code == 422


def test_bloqueio_para_barbeiro_inexistente_retorna_404(client: TestClient):
    assert client.post("/bloqueios", json={"barbeiro_id": 999, "data": DIA}).status_code == 404


def test_intervalo_entre_atendimentos(
    client: TestClient, cenario_api: dict[str, int], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(disponibilidade_service, "CONFIG", Config(intervalo_minutos=15))
    _marcar(client, cenario_api, na_segunda(10))

    livres = _livres(client, cenario_api)

    assert "10:30" not in livres  # 15 minutos de respiro depois do atendimento das 10:00-10:30
    assert "10:45" in livres
    assert "09:30" not in livres  # 09:30-10:00 encostaria no início; precisa do intervalo
    assert "09:00" in livres
    assert _marcar(client, cenario_api, na_segunda(10, 30)).status_code == 409
    assert _marcar(client, cenario_api, na_segunda(10, 45)).status_code == 201
