from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agendamento, Cliente, Servico, StatusAgendamento


def _limites_do_dia(dia: date) -> tuple[datetime, datetime]:
    inicio = datetime.combine(dia, time.min)
    return inicio, inicio + timedelta(days=1)


def adicionar(session: Session, agendamento: Agendamento) -> Agendamento:
    session.add(agendamento)
    session.flush()
    return agendamento


def obter(session: Session, identificador: int) -> Agendamento | None:
    return session.get(Agendamento, identificador)


def _filtrar(
    consulta,
    barbeiro_id: int | None,
    cliente_id: int | None,
    dia: date | None,
    status: StatusAgendamento | None,
    desde: date | None,
):
    if barbeiro_id is not None:
        consulta = consulta.where(Agendamento.barbeiro_id == barbeiro_id)
    if cliente_id is not None:
        consulta = consulta.where(Agendamento.cliente_id == cliente_id)
    if dia is not None:
        inicio_dia, fim_dia = _limites_do_dia(dia)
        consulta = consulta.where(Agendamento.inicio >= inicio_dia, Agendamento.inicio < fim_dia)
    if desde is not None:
        consulta = consulta.where(Agendamento.inicio >= _limites_do_dia(desde)[0])
    if status is not None:
        consulta = consulta.where(Agendamento.status == status)
    return consulta


def listar(
    session: Session,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    dia: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
    limite: int | None = None,
    deslocamento: int = 0,
) -> list[Agendamento]:
    consulta = _filtrar(
        select(Agendamento).order_by(Agendamento.inicio, Agendamento.id),
        barbeiro_id,
        cliente_id,
        dia,
        status,
        desde,
    )
    if limite is not None:
        consulta = consulta.limit(limite).offset(deslocamento)
    return list(session.scalars(consulta))


def contar(
    session: Session,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    dia: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
) -> int:
    consulta = _filtrar(
        select(func.count(Agendamento.id)), barbeiro_id, cliente_id, dia, status, desde
    )
    return session.scalar(consulta) or 0


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


def listar_futuros_do_barbeiro(
    session: Session, barbeiro_id: int, agora: datetime
) -> list[tuple[Agendamento, str, str, Decimal]]:
    consulta = (
        select(Agendamento, Cliente.nome, Servico.nome, Servico.preco)
        .join(Cliente, Cliente.id == Agendamento.cliente_id)
        .join(Servico, Servico.id == Agendamento.servico_id)
        .where(
            Agendamento.barbeiro_id == barbeiro_id,
            Agendamento.status == StatusAgendamento.AGENDADO,
            Agendamento.inicio > agora,
        )
        .order_by(Agendamento.inicio, Agendamento.id)
    )
    return [tuple(linha) for linha in session.execute(consulta)]


def contar_realizados(session: Session, barbeiro_id: int, agora: datetime) -> int:
    consulta = select(func.count(Agendamento.id)).where(
        Agendamento.barbeiro_id == barbeiro_id,
        Agendamento.status == StatusAgendamento.AGENDADO,
        Agendamento.fim <= agora,
    )
    return session.scalar(consulta) or 0
