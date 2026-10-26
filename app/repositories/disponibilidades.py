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
