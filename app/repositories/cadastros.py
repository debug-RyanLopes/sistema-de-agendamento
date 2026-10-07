from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base

Entidade = TypeVar("Entidade", bound=Base)


def adicionar(session: Session, entidade: Entidade) -> Entidade:
    session.add(entidade)
    session.flush()
    return entidade


def listar(session: Session, modelo: type[Entidade]) -> list[Entidade]:
    return list(session.scalars(select(modelo).order_by(modelo.id)))


def obter(session: Session, modelo: type[Entidade], identificador: int) -> Entidade | None:
    return session.get(modelo, identificador)
