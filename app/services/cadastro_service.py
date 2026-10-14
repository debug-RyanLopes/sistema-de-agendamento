from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.errors import RecursoInativoError, RecursoNaoEncontradoError
from app.repositories import cadastros
from app.repositories.cadastros import Entidade


def criar(session: Session, modelo: type[Entidade], dados: BaseModel) -> Entidade:
    entidade = cadastros.adicionar(session, modelo(**dados.model_dump()))
    session.commit()
    return entidade


def listar(
    session: Session, modelo: type[Entidade], incluir_inativos: bool = False
) -> list[Entidade]:
    return cadastros.listar(session, modelo, incluir_inativos)


def obter(
    session: Session, modelo: type[Entidade], identificador: int, rotulo: str
) -> Entidade:
    entidade = cadastros.obter(session, modelo, identificador)
    if entidade is None:
        raise RecursoNaoEncontradoError(f"{rotulo} {identificador} não encontrado")
    return entidade


def obter_ativo(
    session: Session, modelo: type[Entidade], identificador: int, rotulo: str
) -> Entidade:
    entidade = obter(session, modelo, identificador, rotulo)
    if not entidade.ativo:
        raise RecursoInativoError(f"{rotulo} {identificador} está inativo")
    return entidade


def atualizar(
    session: Session,
    modelo: type[Entidade],
    identificador: int,
    dados: BaseModel,
    rotulo: str,
) -> Entidade:
    entidade = obter(session, modelo, identificador, rotulo)
    for campo, valor in dados.model_dump().items():
        setattr(entidade, campo, valor)
    session.commit()
    return entidade


def definir_ativo(
    session: Session,
    modelo: type[Entidade],
    identificador: int,
    ativo: bool,
    rotulo: str,
) -> Entidade:
    entidade = obter(session, modelo, identificador, rotulo)
    entidade.ativo = ativo
    session.commit()
    return entidade
