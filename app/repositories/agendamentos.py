from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Agendamento, Barbeiro, Cliente, Servico, StatusAgendamento


def _limites_do_dia(dia: date) -> tuple[datetime, datetime]:
    inicio = datetime.combine(dia, time.min)
    return inicio, inicio + timedelta(days=1)


def adicionar(session: Session, agendamento: Agendamento) -> Agendamento:
    session.add(agendamento)
    session.flush()
    return agendamento


def obter(session: Session, identificador: int) -> Agendamento | None:
    return session.get(Agendamento, identificador)


def travar_agenda_do_barbeiro(session: Session, barbeiro_id: int) -> None:
    """Bloqueia a linha do barbeiro até o commit (SELECT ... FOR UPDATE).

    No SQLite o FOR UPDATE é ignorado e a serialização vem do BEGIN IMMEDIATE; em
    PostgreSQL é isto que impede dois agendamentos simultâneos para o mesmo barbeiro.
    """
    session.execute(select(Barbeiro.id).where(Barbeiro.id == barbeiro_id).with_for_update())


def _filtrar(
    consulta,
    barbeiro_id: int | None,
    cliente_id: int | None,
    dia: date | None,
    status: StatusAgendamento | None,
    desde: date | None,
    ate: date | None = None,
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
    if ate is not None:
        consulta = consulta.where(Agendamento.inicio < _limites_do_dia(ate)[1])
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
    ate: date | None = None,
) -> list[Agendamento]:
    consulta = _filtrar(
        select(Agendamento).order_by(Agendamento.inicio, Agendamento.id),
        barbeiro_id,
        cliente_id,
        dia,
        status,
        desde,
        ate,
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
    ate: date | None = None,
) -> int:
    consulta = _filtrar(
        select(func.count(Agendamento.id)), barbeiro_id, cliente_id, dia, status, desde, ate
    )
    return session.scalar(consulta) or 0


def listar_detalhado(
    session: Session,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    dia: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
    ate: date | None = None,
) -> list[tuple[Agendamento, str, str, str, Decimal]]:
    """Agendamentos com nome do cliente, do barbeiro, do serviço e preço (para CSV e painel)."""
    consulta = _filtrar(
        select(Agendamento, Cliente.nome, Barbeiro.nome, Servico.nome, Servico.preco)
        .join(Cliente, Cliente.id == Agendamento.cliente_id)
        .join(Barbeiro, Barbeiro.id == Agendamento.barbeiro_id)
        .join(Servico, Servico.id == Agendamento.servico_id)
        .order_by(Agendamento.inicio, Agendamento.id),
        barbeiro_id,
        cliente_id,
        dia,
        status,
        desde,
        ate,
    )
    return [tuple(linha) for linha in session.execute(consulta)]


def existe_sobreposicao(
    session: Session,
    barbeiro_id: int,
    inicio: datetime,
    fim: datetime,
    ignorar_id: int | None = None,
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
    if ignorar_id is not None:
        consulta = consulta.where(Agendamento.id != ignorar_id)
    return session.execute(consulta).first() is not None


def listar_ativos_no_dia(
    session: Session, barbeiro_id: int, dia: date, ignorar_id: int | None = None
) -> list[Agendamento]:
    inicio_dia, fim_dia = _limites_do_dia(dia)
    consulta = select(Agendamento).where(
        Agendamento.barbeiro_id == barbeiro_id,
        Agendamento.status == StatusAgendamento.AGENDADO,
        Agendamento.inicio < fim_dia,
        Agendamento.fim > inicio_dia,
    )
    if ignorar_id is not None:
        consulta = consulta.where(Agendamento.id != ignorar_id)
    return list(session.scalars(consulta))


def contar_ativos_do_cliente(session: Session, cliente_id: int, agora: datetime) -> int:
    consulta = select(func.count(Agendamento.id)).where(
        Agendamento.cliente_id == cliente_id,
        Agendamento.status == StatusAgendamento.AGENDADO,
        Agendamento.inicio > agora,
    )
    return session.scalar(consulta) or 0


def contar_ativos_por_telefone(session: Session, telefone: str, agora: datetime) -> int:
    consulta = (
        select(func.count(Agendamento.id))
        .join(Cliente, Cliente.id == Agendamento.cliente_id)
        .where(
            Cliente.telefone == telefone,
            Agendamento.status == StatusAgendamento.AGENDADO,
            Agendamento.inicio > agora,
        )
    )
    return session.scalar(consulta) or 0


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


def listar_futuros_do_cliente(
    session: Session, cliente_id: int, agora: datetime
) -> list[tuple[Agendamento, str, str, Decimal]]:
    consulta = (
        select(Agendamento, Barbeiro.nome, Servico.nome, Servico.preco)
        .join(Barbeiro, Barbeiro.id == Agendamento.barbeiro_id)
        .join(Servico, Servico.id == Agendamento.servico_id)
        .where(
            Agendamento.cliente_id == cliente_id,
            Agendamento.status == StatusAgendamento.AGENDADO,
            Agendamento.inicio > agora,
        )
        .order_by(Agendamento.inicio, Agendamento.id)
    )
    return [tuple(linha) for linha in session.execute(consulta)]


def _realizado(agora: datetime):
    """Concluído explicitamente, ou agendado cujo horário já passou sem ser cancelado."""
    return or_(
        Agendamento.status == StatusAgendamento.CONCLUIDO,
        (Agendamento.status == StatusAgendamento.AGENDADO) & (Agendamento.fim <= agora),
    )


def contar_realizados(session: Session, barbeiro_id: int, agora: datetime) -> int:
    consulta = select(func.count(Agendamento.id)).where(
        Agendamento.barbeiro_id == barbeiro_id, _realizado(agora)
    )
    return session.scalar(consulta) or 0


def contar_faltas(session: Session, barbeiro_id: int) -> int:
    consulta = select(func.count(Agendamento.id)).where(
        Agendamento.barbeiro_id == barbeiro_id,
        Agendamento.status == StatusAgendamento.NAO_COMPARECEU,
    )
    return session.scalar(consulta) or 0


def listar_para_lembrete(
    session: Session, agora: datetime, ate: datetime
) -> list[tuple[Agendamento, Cliente, str, str, Decimal]]:
    consulta = (
        select(Agendamento, Cliente, Barbeiro.nome, Servico.nome, Servico.preco)
        .join(Cliente, Cliente.id == Agendamento.cliente_id)
        .join(Barbeiro, Barbeiro.id == Agendamento.barbeiro_id)
        .join(Servico, Servico.id == Agendamento.servico_id)
        .where(
            Agendamento.status == StatusAgendamento.AGENDADO,
            Agendamento.lembrete_enviado_em.is_(None),
            Agendamento.inicio > agora,
            Agendamento.inicio <= ate,
        )
        .order_by(Agendamento.inicio)
    )
    return [tuple(linha) for linha in session.execute(consulta)]


def resumo_por_barbeiro(
    session: Session, desde: datetime, ate: datetime
) -> list[tuple[int, str, StatusAgendamento, int, Decimal, int]]:
    """Por barbeiro e status: quantidade, receita (soma dos preços) e minutos ocupados."""
    minutos = func.sum(Agendamento.fim - Agendamento.inicio)
    if session.get_bind().dialect.name == "sqlite":
        minutos = func.sum(
            (func.julianday(Agendamento.fim) - func.julianday(Agendamento.inicio)) * 1440
        )
    consulta = (
        select(
            Barbeiro.id,
            Barbeiro.nome,
            Agendamento.status,
            func.count(Agendamento.id),
            func.coalesce(func.sum(Servico.preco), 0),
            func.coalesce(minutos, 0),
        )
        .join(Barbeiro, Barbeiro.id == Agendamento.barbeiro_id)
        .join(Servico, Servico.id == Agendamento.servico_id)
        .where(Agendamento.inicio >= desde, Agendamento.inicio < ate)
        .group_by(Barbeiro.id, Barbeiro.nome, Agendamento.status)
        .order_by(Barbeiro.nome)
    )
    return [tuple(linha) for linha in session.execute(consulta)]
