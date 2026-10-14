from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base, Cliente

Entidade = TypeVar("Entidade", bound=Base)


def adicionar(session: Session, entidade: Entidade) -> Entidade:
    session.add(entidade)
    session.flush()
    return entidade


def listar(
    session: Session, modelo: type[Entidade], incluir_inativos: bool = False
) -> list[Entidade]:
    consulta = select(modelo).order_by(modelo.id)
    if not incluir_inativos:
        consulta = consulta.where(modelo.ativo.is_(True))
    return list(session.scalars(consulta))


def obter(session: Session, modelo: type[Entidade], identificador: int) -> Entidade | None:
    return session.get(modelo, identificador)


def obter_cliente_por_email(session: Session, email: str) -> Cliente | None:
    consulta = select(Cliente).where(Cliente.email == email).order_by(Cliente.id).limit(1)
    return session.scalars(consulta).first()
