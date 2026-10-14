from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Disponibilidade


def adicionar(session: Session, janela: Disponibilidade) -> Disponibilidade:
    session.add(janela)
    session.flush()
    return janela


def obter(session: Session, janela_id: int) -> Disponibilidade | None:
    return session.get(Disponibilidade, janela_id)


def remover(session: Session, janela: Disponibilidade) -> None:
    session.delete(janela)
    session.flush()


def listar_por_barbeiro(session: Session, barbeiro_id: int) -> list[Disponibilidade]:
    consulta = (
        select(Disponibilidade)
        .where(Disponibilidade.barbeiro_id == barbeiro_id)
        .order_by(Disponibilidade.dia_semana, Disponibilidade.hora_inicio)
    )
    return list(session.scalars(consulta))


def listar_por_dia(session: Session, barbeiro_id: int, dia_semana: int) -> list[Disponibilidade]:
    consulta = (
        select(Disponibilidade)
        .where(
            Disponibilidade.barbeiro_id == barbeiro_id,
            Disponibilidade.dia_semana == dia_semana,
        )
        .order_by(Disponibilidade.hora_inicio)
    )
    return list(session.scalars(consulta))


def cobre(session: Session, barbeiro_id: int, inicio: datetime, fim: datetime) -> bool:
    if inicio.date() != fim.date():
        return False
    consulta = (
        select(Disponibilidade.id)
        .where(
            Disponibilidade.barbeiro_id == barbeiro_id,
            Disponibilidade.dia_semana == inicio.weekday(),
            Disponibilidade.hora_inicio <= inicio.time(),
            Disponibilidade.hora_fim >= fim.time(),
        )
        .limit(1)
    )
    return session.execute(consulta).first() is not None
