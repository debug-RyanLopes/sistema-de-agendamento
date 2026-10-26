from typing import TypeVar

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Base, Cliente

Entidade = TypeVar("Entidade", bound=Base)


def adicionar(session: Session, entidade: Entidade) -> Entidade:
    session.add(entidade)
    session.flush()
    return entidade


def _filtrar(consulta, modelo: type[Entidade], incluir_inativos: bool, busca: str | None):
    if not incluir_inativos:
        consulta = consulta.where(modelo.ativo.is_(True))
    if busca:
        padrao = f"%{busca.strip().lower()}%"
        campos = [func.lower(modelo.nome).like(padrao)]
        if hasattr(modelo, "email"):
            campos.append(func.lower(modelo.email).like(padrao))
        digitos = "".join(filter(str.isdigit, busca))
        if hasattr(modelo, "telefone") and digitos:
            campos.append(modelo.telefone.like(f"%{digitos}%"))
        consulta = consulta.where(or_(*campos))
    return consulta


def listar(
    session: Session,
    modelo: type[Entidade],
    incluir_inativos: bool = False,
    busca: str | None = None,
    limite: int | None = None,
    deslocamento: int = 0,
    recentes_primeiro: bool = False,
) -> list[Entidade]:
    ordem = modelo.id.desc() if recentes_primeiro else modelo.id
    consulta = _filtrar(select(modelo).order_by(ordem), modelo, incluir_inativos, busca)
    if limite is not None:
        consulta = consulta.limit(limite).offset(deslocamento)
    return list(session.scalars(consulta))


def contar(
    session: Session,
    modelo: type[Entidade],
    incluir_inativos: bool = False,
    busca: str | None = None,
) -> int:
    consulta = _filtrar(select(func.count(modelo.id)), modelo, incluir_inativos, busca)
    return session.scalar(consulta) or 0


def obter(session: Session, modelo: type[Entidade], identificador: int) -> Entidade | None:
    return session.get(modelo, identificador)


def obter_cliente_por_email(session: Session, email: str) -> Cliente | None:
    consulta = select(Cliente).where(Cliente.email == email).order_by(Cliente.id).limit(1)
    return session.scalars(consulta).first()


def existe_com_valor(
    session: Session,
    modelo: type[Entidade],
    campo: str,
    valor: str,
    ignorar_id: int | None = None,
) -> bool:
    consulta = select(modelo.id).where(getattr(modelo, campo) == valor).limit(1)
    if ignorar_id is not None:
        consulta = consulta.where(modelo.id != ignorar_id)
    return session.execute(consulta).first() is not None
