from fastapi import APIRouter
from pydantic import BaseModel

from app.dependencies import SessaoDep
from app.models import Barbeiro, Base, Cliente, Produto, Servico
from app.schemas import (
    ERRO_404,
    ERRO_422,
    AtivoIn,
    BarbeiroIn,
    BarbeiroOut,
    ClienteIn,
    ClienteOut,
    ProdutoIn,
    ProdutoOut,
    ServicoIn,
    ServicoOut,
)
from app.services import cadastro_service


def criar_router_cadastro(
    *,
    prefixo: str,
    tag: str,
    modelo: type[Base],
    entrada: type[BaseModel],
    saida: type[BaseModel],
    rotulo: str,
) -> APIRouter:
    router = APIRouter(prefix=prefixo, tags=[tag])

    @router.post(
        "",
        response_model=saida,
        status_code=201,
        responses=ERRO_422,
        summary=f"Cadastrar {rotulo}",
    )
    def criar(dados: entrada, sessao: SessaoDep):
        return cadastro_service.criar(sessao, modelo, dados)

    @router.get("", response_model=list[saida], summary=f"Listar {rotulo}s")
    def listar(sessao: SessaoDep, incluir_inativos: bool = False):
        return cadastro_service.listar(sessao, modelo, incluir_inativos)

    @router.get(
        "/{identificador}", response_model=saida, responses=ERRO_404, summary=f"Consultar {rotulo}"
    )
    def obter(identificador: int, sessao: SessaoDep):
        return cadastro_service.obter(sessao, modelo, identificador, rotulo)

    @router.put(
        "/{identificador}",
        response_model=saida,
        responses={**ERRO_404, **ERRO_422},
        summary=f"Editar {rotulo}",
    )
    def atualizar(identificador: int, dados: entrada, sessao: SessaoDep):
        return cadastro_service.atualizar(sessao, modelo, identificador, dados, rotulo)

    @router.patch(
        "/{identificador}/ativo",
        response_model=saida,
        responses=ERRO_404,
        summary=f"Ativar ou desativar {rotulo}",
    )
    def definir_ativo(identificador: int, dados: AtivoIn, sessao: SessaoDep):
        return cadastro_service.definir_ativo(sessao, modelo, identificador, dados.ativo, rotulo)

    return router


clientes = criar_router_cadastro(
    prefixo="/clientes", tag="clientes", modelo=Cliente, entrada=ClienteIn, saida=ClienteOut,
    rotulo="cliente",
)
barbeiros = criar_router_cadastro(
    prefixo="/barbeiros", tag="barbeiros", modelo=Barbeiro, entrada=BarbeiroIn,
    saida=BarbeiroOut, rotulo="barbeiro",
)
servicos = criar_router_cadastro(
    prefixo="/servicos", tag="serviços", modelo=Servico, entrada=ServicoIn, saida=ServicoOut,
    rotulo="serviço",
)
produtos = criar_router_cadastro(
    prefixo="/produtos", tag="produtos", modelo=Produto, entrada=ProdutoIn, saida=ProdutoOut,
    rotulo="produto",
)
