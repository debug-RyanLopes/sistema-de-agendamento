from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Bloqueio


def adicionar(session: Session, bloqueio: Bloqueio) -> Bloqueio:
    session.add(bloqueio)
    session.flush()
    return bloqueio


def obter(session: Session, bloqueio_id: int) -> Bloqueio | None:
    return session.get(Bloqueio, bloqueio_id)


def remover(session: Session, bloqueio: Bloqueio) -> None:
    session.delete(bloqueio)
    session.flush()


def listar(
    session: Session, desde: date | None = None, barbeiro_id: int | None = None
) -> list[Bloqueio]:
    consulta = select(Bloqueio).order_by(Bloqueio.data, Bloqueio.hora_inicio, Bloqueio.id)
    if desde is not None:
        consulta = consulta.where(Bloqueio.data >= desde)
    if barbeiro_id is not None:
        consulta = consulta.where(
            or_(Bloqueio.barbeiro_id == barbeiro_id, Bloqueio.barbeiro_id.is_(None))
        )
    return list(session.scalars(consulta))


def listar_do_dia(session: Session, barbeiro_id: int, dia: date) -> list[Bloqueio]:
    """Bloqueios que valem para este barbeiro no dia: os dele e os da barbearia toda."""
    consulta = select(Bloqueio).where(
        Bloqueio.data == dia,
        or_(Bloqueio.barbeiro_id == barbeiro_id, Bloqueio.barbeiro_id.is_(None)),
    )
    return list(session.scalars(consulta))
