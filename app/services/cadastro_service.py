from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import iniciar_escrita
from app.errors import (
    RecursoDuplicadoError,
    RecursoInativoError,
    RecursoNaoEncontradoError,
    TransicaoInvalidaError,
)
from app.models import Barbeiro, Cliente
from app.repositories import agendamentos, cadastros
from app.repositories.cadastros import Entidade

CAMPOS_UNICOS = {Cliente: "email", Barbeiro: "email"}


def _garantir_unicidade(
    session: Session,
    modelo: type[Entidade],
    dados: BaseModel,
    ignorar_id: int | None = None,
) -> None:
    campo = CAMPOS_UNICOS.get(modelo)
    if campo is None:
        return
    valor = getattr(dados, campo)
    if cadastros.existe_com_valor(session, modelo, campo, valor, ignorar_id):
        raise RecursoDuplicadoError(f"já existe um cadastro com este {campo}: {valor}")


def criar(session: Session, modelo: type[Entidade], dados: BaseModel) -> Entidade:
    iniciar_escrita(session)
    _garantir_unicidade(session, modelo, dados)
    entidade = cadastros.adicionar(session, modelo(**dados.model_dump()))
    session.commit()
    return entidade


def listar(
    session: Session,
    modelo: type[Entidade],
    incluir_inativos: bool = False,
    busca: str | None = None,
    limite: int | None = None,
    deslocamento: int = 0,
    recentes_primeiro: bool = False,
) -> list[Entidade]:
    return cadastros.listar(
        session, modelo, incluir_inativos, busca, limite, deslocamento, recentes_primeiro
    )


def contar(
    session: Session,
    modelo: type[Entidade],
    incluir_inativos: bool = False,
    busca: str | None = None,
) -> int:
    return cadastros.contar(session, modelo, incluir_inativos, busca)


def obter(session: Session, modelo: type[Entidade], identificador: int, rotulo: str) -> Entidade:
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
    iniciar_escrita(session)
    entidade = obter(session, modelo, identificador, rotulo)
    _garantir_unicidade(session, modelo, dados, ignorar_id=identificador)
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
    iniciar_escrita(session)
    entidade = obter(session, modelo, identificador, rotulo)
    entidade.ativo = ativo
    session.commit()
    return entidade


def anonimizar_cliente(session: Session, cliente_id: int, agora: datetime) -> Cliente:
    """Apaga os dados pessoais mantendo o histórico de agendamentos (LGPD, art. 18).

    O registro continua existindo com um nome genérico, e-mail inválido e telefone zerado,
    para que relatórios e o histórico dos barbeiros não quebrem.
    """
    iniciar_escrita(session)
    cliente = obter(session, Cliente, cliente_id, "cliente")
    if agendamentos.contar_ativos_do_cliente(session, cliente_id, agora):
        raise TransicaoInvalidaError(
            "o cliente tem agendamentos futuros; cancele-os antes de apagar os dados"
        )
    cliente.nome = "Cliente removido"
    cliente.email = f"removido-{cliente.id}@anonimo.invalid"
    cliente.telefone = "0000000000"
    cliente.ativo = False
    cliente.anonimizado_em = agora
    session.commit()
    return cliente
