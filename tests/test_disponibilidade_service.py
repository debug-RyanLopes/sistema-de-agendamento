from datetime import time

import pytest
from sqlalchemy.orm import Session

from app.errors import RecursoNaoEncontradoError
from app.models import Barbeiro, Disponibilidade
from app.schemas import AgendamentoIn, DisponibilidadeIn
from app.services import agendamento_service, disponibilidade_service
from tests.conftest import Cenario
from tests.helpers import AGORA_FIXO, DOMINGO, SEGUNDA, na_segunda

SLOT = 15


def _barbeiro_com_janela(session: Session, inicio: time, fim: time) -> Barbeiro:
    barbeiro = Barbeiro(nome="Pedro Navalha", email="pedro@barbearia.com")
    session.add(barbeiro)
    session.flush()
    session.add(
        Disponibilidade(barbeiro_id=barbeiro.id, dia_semana=0, hora_inicio=inicio, hora_fim=fim)
    )
    session.commit()
    return barbeiro


def _livres(session: Session, barbeiro_id: int, servico_id: int, agora=AGORA_FIXO):
    return disponibilidade_service.horarios_livres(
        session, barbeiro_id, servico_id, SEGUNDA.date(), agora, SLOT
    )


def test_gera_slots_de_15_minutos_que_cabem_na_janela(session: Session, cenario: Cenario):
    barbeiro = _barbeiro_com_janela(session, time(9, 0), time(12, 0))

    livres = _livres(session, barbeiro.id, cenario.servico_30.id)

    assert len(livres) == 11
    assert livres[0] == na_segunda(9)
    assert livres[-1] == na_segunda(11, 30)


def test_servico_mais_longo_reduz_os_slots(session: Session, cenario: Cenario):
    barbeiro = _barbeiro_com_janela(session, time(9, 0), time(12, 0))

    livres = _livres(session, barbeiro.id, cenario.servico_60.id)

    assert livres[-1] == na_segunda(11)
    assert len(livres) == 9


def test_exclui_slots_que_sobrepoem_agendamento_existente(session: Session, cenario: Cenario):
    barbeiro = _barbeiro_com_janela(session, time(9, 0), time(12, 0))
    agendamento_service.criar(
        session,
        AgendamentoIn(
            cliente_id=cenario.cliente.id,
            barbeiro_id=barbeiro.id,
            servico_id=cenario.servico_30.id,
            inicio=na_segunda(10),
        ),
        AGORA_FIXO,
    )

    livres = _livres(session, barbeiro.id, cenario.servico_30.id)

    assert na_segunda(9, 30) in livres
    assert na_segunda(10, 30) in livres
    for ocupado in (na_segunda(9, 45), na_segunda(10), na_segunda(10, 15)):
        assert ocupado not in livres


def test_exclui_horarios_que_ja_passaram(session: Session, cenario: Cenario):
    barbeiro = _barbeiro_com_janela(session, time(9, 0), time(12, 0))

    livres = _livres(session, barbeiro.id, cenario.servico_30.id, agora=na_segunda(10, 7))

    assert livres[0] == na_segunda(10, 15)


def test_alinha_slots_ao_relogio_quando_a_janela_nao_e_multipla(
    session: Session, cenario: Cenario
):
    barbeiro = _barbeiro_com_janela(session, time(9, 10), time(11, 0))

    livres = _livres(session, barbeiro.id, cenario.servico_30.id)

    assert livres[0] == na_segunda(9, 15)


def test_dia_sem_janela_retorna_lista_vazia(session: Session, cenario: Cenario):
    livres = disponibilidade_service.horarios_livres(
        session, cenario.barbeiro.id, cenario.servico_30.id, DOMINGO.date(), AGORA_FIXO, SLOT
    )

    assert livres == []


def test_janelas_sobrepostas_nao_duplicam_slots(session: Session, cenario: Cenario):
    session.add(
        Disponibilidade(
            barbeiro_id=cenario.barbeiro.id,
            dia_semana=0,
            hora_inicio=time(9, 0),
            hora_fim=time(12, 0),
        )
    )
    session.commit()

    livres = _livres(session, cenario.barbeiro.id, cenario.servico_30.id)

    assert len(livres) == len(set(livres))


@pytest.mark.parametrize("barbeiro_id,servico_id", [(999, 1), (1, 999)])
def test_barbeiro_ou_servico_inexistente_levanta_nao_encontrado(
    session: Session, cenario: Cenario, barbeiro_id: int, servico_id: int
):
    with pytest.raises(RecursoNaoEncontradoError):
        _livres(session, barbeiro_id, servico_id)


def test_cadastrar_e_listar_janelas(session: Session, cenario: Cenario):
    disponibilidade_service.cadastrar_janela(
        session,
        cenario.barbeiro.id,
        DisponibilidadeIn(dia_semana=1, hora_inicio=time(10, 0), hora_fim=time(16, 0)),
    )

    janelas = disponibilidade_service.listar_janelas(session, cenario.barbeiro.id)

    assert [janela.dia_semana for janela in janelas] == [0, 1]


def test_cadastrar_janela_para_barbeiro_inexistente_levanta_nao_encontrado(session: Session):
    with pytest.raises(RecursoNaoEncontradoError):
        disponibilidade_service.cadastrar_janela(
            session,
            999,
            DisponibilidadeIn(dia_semana=1, hora_inicio=time(10, 0), hora_fim=time(16, 0)),
        )
