from datetime import datetime, time

import pytest
from app.errors import (
    ConflitoHorarioError,
    ForaDaDisponibilidadeError,
    HorarioPassadoError,
    RecursoNaoEncontradoError,
)
from app.models import Barbeiro, Disponibilidade, StatusAgendamento
from app.schemas import AgendamentoIn
from app.services import agendamento_service
from sqlalchemy.orm import Session

from tests.conftest import Cenario
from tests.helpers import AGORA_FIXO, DOMINGO, na_segunda


def _dados(cenario: Cenario, inicio: datetime, servico: str = "servico_30") -> AgendamentoIn:
    return AgendamentoIn(
        cliente_id=cenario.cliente.id,
        barbeiro_id=cenario.barbeiro.id,
        servico_id=getattr(cenario, servico).id,
        inicio=inicio,
    )


def test_cria_agendamento_calcula_fim_e_dados_de_confirmacao(session: Session, cenario: Cenario):
    agendamento, confirmacao = agendamento_service.criar(
        session, _dados(cenario, na_segunda(10)), AGORA_FIXO
    )

    assert agendamento.id is not None
    assert agendamento.fim == na_segunda(10, 30)
    assert agendamento.status == StatusAgendamento.AGENDADO
    assert confirmacao.email == "carlos@exemplo.com"
    assert confirmacao.cliente == "Carlos Silva"
    assert confirmacao.barbeiro == "João Barbeiro"
    assert confirmacao.servico == "Corte de cabelo"
    assert confirmacao.inicio == na_segunda(10)
    assert confirmacao.preco == 45.0


@pytest.mark.parametrize(
    ("existente", "hora", "minuto", "novo"),
    [
        ("servico_30", 10, 15, "servico_30"),
        ("servico_30", 10, 0, "servico_30"),
        ("servico_30", 9, 45, "servico_30"),
        ("servico_30", 9, 30, "servico_60"),
        ("servico_60", 10, 15, "servico_30"),
    ],
    ids=["parcial-depois", "total", "parcial-antes", "novo-envolve", "novo-contido"],
)
def test_sobreposicao_levanta_conflito_e_nao_grava(
    session: Session, cenario: Cenario, existente: str, hora: int, minuto: int, novo: str
):
    agendamento_service.criar(session, _dados(cenario, na_segunda(10), existente), AGORA_FIXO)

    with pytest.raises(ConflitoHorarioError):
        agendamento_service.criar(
            session, _dados(cenario, na_segunda(hora, minuto), novo), AGORA_FIXO
        )

    assert len(agendamento_service.listar(session)) == 1


def test_intervalo_encostado_e_permitido(session: Session, cenario: Cenario):
    agendamento_service.criar(session, _dados(cenario, na_segunda(10)), AGORA_FIXO)

    depois, _ = agendamento_service.criar(session, _dados(cenario, na_segunda(10, 30)), AGORA_FIXO)
    antes, _ = agendamento_service.criar(session, _dados(cenario, na_segunda(9, 30)), AGORA_FIXO)

    assert depois.inicio == na_segunda(10, 30)
    assert antes.fim == na_segunda(10)


def test_agendamento_cancelado_nao_conta_para_conflito(session: Session, cenario: Cenario):
    primeiro, _ = agendamento_service.criar(session, _dados(cenario, na_segunda(10)), AGORA_FIXO)
    agendamento_service.cancelar(session, primeiro.id, AGORA_FIXO)[0]

    segundo, _ = agendamento_service.criar(session, _dados(cenario, na_segunda(10)), AGORA_FIXO)

    assert segundo.status == StatusAgendamento.AGENDADO


def test_mesmo_horario_com_outro_barbeiro_e_permitido(session: Session, cenario: Cenario):
    outro = Barbeiro(nome="Pedro Navalha", email="pedro@barbearia.com")
    session.add(outro)
    session.flush()
    session.add(
        Disponibilidade(
            barbeiro_id=outro.id,
            dia_semana=0,
            hora_inicio=time(9, 0),
            hora_fim=time(18, 0),
        )
    )
    session.commit()
    agendamento_service.criar(session, _dados(cenario, na_segunda(10)), AGORA_FIXO)

    dados_outro = AgendamentoIn(
        cliente_id=cenario.cliente.id,
        barbeiro_id=outro.id,
        servico_id=cenario.servico_30.id,
        inicio=na_segunda(10),
    )
    agendamento, _ = agendamento_service.criar(session, dados_outro, AGORA_FIXO)

    assert agendamento.barbeiro_id == outro.id


@pytest.mark.parametrize(
    "inicio",
    [datetime(2029, 12, 31, 10, 0), AGORA_FIXO],
    ids=["antes-de-agora", "exatamente-agora"],
)
def test_horario_no_passado_levanta_erro(session: Session, cenario: Cenario, inicio: datetime):
    with pytest.raises(HorarioPassadoError):
        agendamento_service.criar(session, _dados(cenario, inicio), AGORA_FIXO)


@pytest.mark.parametrize(
    "inicio",
    [na_segunda(18), DOMINGO.replace(hour=10), na_segunda(8, 45), na_segunda(17, 45)],
    ids=["no-fim-da-janela", "domingo-sem-janela", "antes-da-janela", "fim-excede-janela"],
)
def test_fora_da_disponibilidade_levanta_erro(
    session: Session, cenario: Cenario, inicio: datetime
):
    with pytest.raises(ForaDaDisponibilidadeError):
        agendamento_service.criar(session, _dados(cenario, inicio), AGORA_FIXO)


def test_ultimo_horario_que_cabe_na_janela_e_aceito(session: Session, cenario: Cenario):
    agendamento, _ = agendamento_service.criar(
        session, _dados(cenario, na_segunda(17, 30)), AGORA_FIXO
    )

    assert agendamento.fim == na_segunda(18)


@pytest.mark.parametrize("campo", ["cliente_id", "barbeiro_id", "servico_id"])
def test_recurso_inexistente_levanta_nao_encontrado(
    session: Session, cenario: Cenario, campo: str
):
    dados = _dados(cenario, na_segunda(10)).model_copy(update={campo: 999})

    with pytest.raises(RecursoNaoEncontradoError):
        agendamento_service.criar(session, dados, AGORA_FIXO)


def test_cancelar_muda_status_e_e_idempotente(session: Session, cenario: Cenario):
    agendamento, _ = agendamento_service.criar(
        session, _dados(cenario, na_segunda(10)), AGORA_FIXO
    )

    primeiro = agendamento_service.cancelar(session, agendamento.id, AGORA_FIXO)[0]
    segundo = agendamento_service.cancelar(session, agendamento.id, AGORA_FIXO)[0]

    assert primeiro.status == StatusAgendamento.CANCELADO
    assert segundo.status == StatusAgendamento.CANCELADO


def test_cancelar_inexistente_levanta_nao_encontrado(session: Session):
    with pytest.raises(RecursoNaoEncontradoError):
        agendamento_service.cancelar(session, 999, AGORA_FIXO)[0]


def test_listar_filtra_por_barbeiro_cliente_e_dia(session: Session, cenario: Cenario):
    agendamento_service.criar(session, _dados(cenario, na_segunda(10)), AGORA_FIXO)
    agendamento_service.criar(session, _dados(cenario, na_segunda(11)), AGORA_FIXO)

    assert len(agendamento_service.listar(session)) == 2
    assert len(agendamento_service.listar(session, barbeiro_id=cenario.barbeiro.id)) == 2
    assert agendamento_service.listar(session, barbeiro_id=999) == []
    assert agendamento_service.listar(session, cliente_id=999) == []
    assert len(agendamento_service.listar(session, dia=na_segunda(0).date())) == 2
    assert agendamento_service.listar(session, dia=DOMINGO.date()) == []
