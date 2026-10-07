from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.errors import RecursoNaoEncontradoError
from app.repositories import cadastros
from app.repositories.cadastros import Entidade


def criar(session: Session, modelo: type[Entidade], dados: BaseModel) -> Entidade:
    entidade = cadastros.adicionar(session, modelo(**dados.model_dump()))
    session.commit()
    return entidade


def listar(session: Session, modelo: type[Entidade]) -> list[Entidade]:
    return cadastros.listar(session, modelo)


def obter(
    session: Session, modelo: type[Entidade], identificador: int, rotulo: str
) -> Entidade:
    entidade = cadastros.obter(session, modelo, identificador)
    if entidade is None:
        raise RecursoNaoEncontradoError(f"{rotulo} {identificador} não encontrado")
    return entidade
