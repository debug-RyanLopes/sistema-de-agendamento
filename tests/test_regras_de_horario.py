from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_agora
from app.errors import DataForaDaJanelaError, HorarioInvalidoError
from app.schemas import AgendamentoIn, AgendamentoPublicoIn
from app.services import agendamento_service, disponibilidade_service
from app.tempo import agora_local, ultimo_dia_do_mes
from tests.conftest import Cenario
from tests.helpers import AGORA_FIXO, na_segunda


def _publico(cenario: Cenario, inicio: datetime) -> AgendamentoPublicoIn:
    return AgendamentoPublicoIn(
        nome="Maria Nova",
        email="maria@exemplo.com",
        telefone="11911112222",
        barbeiro_id=cenario.barbeiro.id,
        servico_id=cenario.servico_30.id,
        inicio=inicio,
    )


def _corpo_admin(ids: dict[str, int], inicio: str) -> dict:
    return {
        "cliente_id": ids["cliente_id"],
        "barbeiro_id": ids["barbeiro_id"],
        "servico_id": ids["servico_30_id"],
        "inicio": inicio,
    }


@pytest.mark.parametrize(
    ("momento", "esperado"),
    [
        (datetime(2030, 1, 7, 10, 0), True),
        (datetime(2030, 1, 7, 10, 15), True),
        (datetime(2030, 1, 7, 10, 30), True),
        (datetime(2030, 1, 7, 10, 7), False),
        (datetime(2030, 1, 7, 10, 0, 30), False),
        (datetime(2030, 1, 7, 10, 0, 0, 5), False),
    ],
)
def test_alinhamento_com_slot_de_15_minutos(momento: datetime, esperado: bool):
    assert disponibilidade_service.horario_alinhado(momento, 15) is esperado


def test_alinhamento_respeita_o_slot_informado():
    assert disponibilidade_service.horario_alinhado(datetime(2030, 1, 7, 10, 20), 20)
    assert not disponibilidade_service.horario_alinhado(datetime(2030, 1, 7, 10, 15), 20)


def test_alinhamento_usa_o_slot_da_configuracao_quando_nao_informado():
    assert disponibilidade_service.horario_alinhado(datetime(2030, 1, 7, 10, 15))
    assert not disponibilidade_service.horario_alinhado(datetime(2030, 1, 7, 10, 7))


def test_servico_rejeita_horario_fora_da_grade(session: Session, cenario: Cenario):
    dados = AgendamentoIn(
        cliente_id=cenario.cliente.id,
        barbeiro_id=cenario.barbeiro.id,
        servico_id=cenario.servico_30.id,
        inicio=na_segunda(10, 7),
    )

    with pytest.raises(HorarioInvalidoError, match="múltiplos de 15"):
        agendamento_service.criar(session, dados, AGORA_FIXO)


def test_servico_publico_rejeita_horario_fora_da_grade_e_nao_grava(
    session: Session, cenario: Cenario
):
    with pytest.raises(HorarioInvalidoError):
        agendamento_service.criar_publico(
            session, _publico(cenario, na_segunda(10, 7)), AGORA_FIXO
        )

    assert agendamento_service.listar(session) == []


def test_slot_customizado_vale_para_a_criacao(session: Session, cenario: Cenario):
    agendamento, _ = agendamento_service.criar_publico(
        session, _publico(cenario, na_segunda(10, 20)), AGORA_FIXO, slot_minutos=20
    )

    assert agendamento.inicio == na_segunda(10, 20)


def test_api_devolve_422_e_nao_fragmenta_a_agenda(
    client: TestClient, cenario_api: dict[str, int]
):
    torto = client.post("/agendamentos", json=_corpo_admin(cenario_api, "2030-01-07T10:07:00"))
    certo = client.post("/agendamentos", json=_corpo_admin(cenario_api, "2030-01-07T10:00:00"))

    assert torto.status_code == 422
    assert "múltiplos de 15" in torto.json()["detail"]
    assert certo.status_code == 201


def test_ultimo_dia_do_mes():
    assert ultimo_dia_do_mes(date(2030, 1, 15)) == date(2030, 1, 31)
    assert ultimo_dia_do_mes(date(2028, 2, 1)) == date(2028, 2, 29)
    assert ultimo_dia_do_mes(date(2030, 2, 1)) == date(2030, 2, 28)
    assert ultimo_dia_do_mes(date(2030, 12, 31)) == date(2030, 12, 31)


def test_janela_aceita_de_hoje_ate_o_ultimo_dia_do_mes():
    disponibilidade_service.validar_janela_de_datas(date(2030, 1, 1), AGORA_FIXO)
    disponibilidade_service.validar_janela_de_datas(date(2030, 1, 31), AGORA_FIXO)


@pytest.mark.parametrize("dia", [date(2029, 12, 31), date(2030, 2, 1), date(1, 1, 1)])
def test_janela_rejeita_datas_fora_do_intervalo(dia: date):
    with pytest.raises(DataForaDaJanelaError, match="01/01/2030 e 31/01/2030"):
        disponibilidade_service.validar_janela_de_datas(dia, AGORA_FIXO)


def test_janela_acompanha_o_dia_corrente():
    agora = datetime(2030, 1, 15, 9, 0)

    disponibilidade_service.validar_janela_de_datas(date(2030, 1, 31), agora)
    with pytest.raises(DataForaDaJanelaError):
        disponibilidade_service.validar_janela_de_datas(date(2030, 2, 1), agora)
    with pytest.raises(DataForaDaJanelaError):
        disponibilidade_service.validar_janela_de_datas(date(2030, 1, 14), agora)


def test_consulta_do_cliente_so_vale_dentro_da_janela(
    client_publico: TestClient, cenario: Cenario
):
    def consultar(dia: str):
        return client_publico.get(
            "/disponibilidade", params={"data": dia, "servico_id": cenario.servico_30.id}
        )

    proximo_mes = consultar("2030-02-04")

    assert proximo_mes.status_code == 422
    assert "31/01/2030" in proximo_mes.json()["detail"]
    assert consultar("2029-12-31").status_code == 422
    assert consultar("2030-01-31").status_code == 200


def test_marcar_alem_do_fim_do_mes_devolve_422(client_publico: TestClient, cenario: Cenario):
    resposta = client_publico.post(
        "/agendamentos",
        json={
            "nome": "Maria Nova",
            "email": "maria@exemplo.com",
            "telefone": "11911112222",
            "barbeiro_id": cenario.barbeiro.id,
            "servico_id": cenario.servico_30.id,
            "inicio": "2030-02-04T10:00:00",
        },
    )

    assert resposta.status_code == 422
    assert "31/01/2030" in resposta.json()["detail"]


def test_empresa_continua_podendo_agendar_alem_do_mes(
    client: TestClient, cenario_api: dict[str, int]
):
    resposta = client.post("/agendamentos", json=_corpo_admin(cenario_api, "2030-02-04T10:00:00"))

    assert resposta.status_code == 201


def test_agora_local_e_o_horario_de_manaus_sem_fuso_no_valor():
    manaus = timezone(timedelta(hours=-4))

    esperado = datetime.now(manaus).replace(tzinfo=None)
    obtido = agora_local()

    assert obtido.tzinfo is None
    assert abs(obtido - esperado) < timedelta(seconds=5)


def test_dependencia_get_agora_usa_o_fuso_de_manaus():
    assert abs(get_agora() - agora_local()) < timedelta(seconds=5)


def test_entrada_com_fuso_e_rejeitada(client: TestClient, cenario_api: dict[str, int]):
    resposta = client.post(
        "/agendamentos", json=_corpo_admin(cenario_api, "2030-01-07T10:00:00-03:00")
    )

    assert resposta.status_code == 422
    assert "Manaus" in resposta.text
