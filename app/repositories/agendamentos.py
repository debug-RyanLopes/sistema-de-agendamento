from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agendamento, StatusAgendamento


def _limites_do_dia(dia: date) -> tuple[datetime, datetime]:
    inicio = datetime.combine(dia, time.min)
    return inicio, inicio + timedelta(days=1)


def adicionar(session: Session, agendamento: Agendamento) -> Agendamento:
    session.add(agendamento)
    session.flush()
    return agendamento


def obter(session: Session, identificador: int) -> Agendamento | None:
    return session.get(Agendamento, identificador)


def listar(
    session: Session,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    dia: date | None = None,
) -> list[Agendamento]:
    consulta = select(Agendamento).order_by(Agendamento.inicio, Agendamento.id)
    if barbeiro_id is not None:
        consulta = consulta.where(Agendamento.barbeiro_id == barbeiro_id)
    if cliente_id is not None:
        consulta = consulta.where(Agendamento.cliente_id == cliente_id)
    if dia is not None:
        inicio_dia, fim_dia = _limites_do_dia(dia)
        consulta = consulta.where(Agendamento.inicio >= inicio_dia, Agendamento.inicio < fim_dia)
    return list(session.scalars(consulta))


def existe_sobreposicao(
    session: Session, barbeiro_id: int, inicio: datetime, fim: datetime
) -> bool:
    consulta = (
        select(Agendamento.id)
        .where(
            Agendamento.barbeiro_id == barbeiro_id,
            Agendamento.status == StatusAgendamento.AGENDADO,
            Agendamento.inicio < fim,
            Agendamento.fim > inicio,
        )
        .limit(1)
    )
    return session.execute(consulta).first() is not None


def listar_ativos_no_dia(session: Session, barbeiro_id: int, dia: date) -> list[Agendamento]:
    inicio_dia, fim_dia = _limites_do_dia(dia)
    consulta = select(Agendamento).where(
        Agendamento.barbeiro_id == barbeiro_id,
        Agendamento.status == StatusAgendamento.AGENDADO,
        Agendamento.inicio < fim_dia,
        Agendamento.fim > inicio_dia,
    )
    return list(session.scalars(consulta))
