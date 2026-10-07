from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.errors import (
    ConflitoHorarioError,
    ForaDaDisponibilidadeError,
    HorarioPassadoError,
    RecursoNaoEncontradoError,
)
from app.models import Agendamento, Barbeiro, Cliente, Servico, StatusAgendamento
from app.repositories import agendamentos, disponibilidades
from app.schemas import AgendamentoIn
from app.services import cadastro_service
from app.services.notificacao_service import DadosConfirmacao


def criar(
    session: Session, dados: AgendamentoIn, agora: datetime
) -> tuple[Agendamento, DadosConfirmacao]:
    cliente = cadastro_service.obter(session, Cliente, dados.cliente_id, "cliente")
    barbeiro = cadastro_service.obter(session, Barbeiro, dados.barbeiro_id, "barbeiro")
    servico = cadastro_service.obter(session, Servico, dados.servico_id, "serviço")

    inicio = dados.inicio
    fim = inicio + timedelta(minutes=servico.duracao_minutos)

    if inicio <= agora:
        raise HorarioPassadoError("o horário escolhido já passou")
    if not disponibilidades.cobre(session, barbeiro.id, inicio, fim):
        raise ForaDaDisponibilidadeError("o horário está fora da disponibilidade do barbeiro")
    if agendamentos.existe_sobreposicao(session, barbeiro.id, inicio, fim):
        raise ConflitoHorarioError("o barbeiro já tem um agendamento nesse horário")

    agendamento = agendamentos.adicionar(
        session,
        Agendamento(
            cliente_id=cliente.id,
            barbeiro_id=barbeiro.id,
            servico_id=servico.id,
            inicio=inicio,
            fim=fim,
            status=StatusAgendamento.AGENDADO,
        ),
    )
    session.commit()
    confirmacao = DadosConfirmacao(
        email=cliente.email,
        cliente=cliente.nome,
        barbeiro=barbeiro.nome,
        servico=servico.nome,
        inicio=inicio,
        preco=servico.preco,
    )
    return agendamento, confirmacao


def cancelar(session: Session, agendamento_id: int) -> Agendamento:
    agendamento = obter(session, agendamento_id)
    if agendamento.status == StatusAgendamento.AGENDADO:
        agendamento.status = StatusAgendamento.CANCELADO
        session.commit()
    return agendamento


def obter(session: Session, agendamento_id: int) -> Agendamento:
    agendamento = agendamentos.obter(session, agendamento_id)
    if agendamento is None:
        raise RecursoNaoEncontradoError(f"agendamento {agendamento_id} não encontrado")
    return agendamento


def listar(
    session: Session,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    dia: date | None = None,
) -> list[Agendamento]:
    return agendamentos.listar(session, barbeiro_id, cliente_id, dia)
