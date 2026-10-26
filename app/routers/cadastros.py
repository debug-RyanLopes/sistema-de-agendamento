from typing import Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app.dependencies import AgoraDep, SessaoDep, SomenteDono
from app.models import Barbeiro, Base, Cliente, Produto, Servico
from app.schemas import (
    ERRO_403,
    ERRO_404,
    ERRO_409,
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

LIMITE_MAXIMO = 500


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
        responses={**ERRO_403, **ERRO_409, **ERRO_422},
        summary=f"Cadastrar {rotulo}",
        dependencies=[SomenteDono],
    )
    def criar(dados: entrada, sessao: SessaoDep):
        return cadastro_service.criar(sessao, modelo, dados)

    @router.get(
        "",
        response_model=list[saida],
        summary=f"Listar {rotulo}s",
        description="Aceita `busca` (nome, e-mail ou telefone), `limite`, `deslocamento` e "
        "`ordem` (`id` ou `recentes`). O total que atende ao filtro vem no cabeçalho "
        "`X-Total-Count`.",
    )
    def listar(
        sessao: SessaoDep,
        resposta: Response,
        incluir_inativos: bool = False,
        busca: str | None = Query(None, max_length=100),
        limite: int | None = Query(None, ge=1, le=LIMITE_MAXIMO),
        deslocamento: int = Query(0, ge=0),
        ordem: Literal["id", "recentes"] = "id",
    ):
        itens = cadastro_service.listar(
            sessao, modelo, incluir_inativos, busca, limite, deslocamento, ordem == "recentes"
        )
        resposta.headers["X-Total-Count"] = str(
            cadastro_service.contar(sessao, modelo, incluir_inativos, busca)
        )
        return itens

    @router.get(
        "/{identificador}", response_model=saida, responses=ERRO_404, summary=f"Consultar {rotulo}"
    )
    def obter(identificador: int, sessao: SessaoDep):
        return cadastro_service.obter(sessao, modelo, identificador, rotulo)

    @router.put(
        "/{identificador}",
        response_model=saida,
        responses={**ERRO_403, **ERRO_404, **ERRO_409, **ERRO_422},
        summary=f"Editar {rotulo}",
        dependencies=[SomenteDono],
    )
    def atualizar(identificador: int, dados: entrada, sessao: SessaoDep):
        return cadastro_service.atualizar(sessao, modelo, identificador, dados, rotulo)

    @router.patch(
        "/{identificador}/ativo",
        response_model=saida,
        responses={**ERRO_403, **ERRO_404},
        summary=f"Ativar ou desativar {rotulo}",
        dependencies=[SomenteDono],
    )
    def definir_ativo(identificador: int, dados: AtivoIn, sessao: SessaoDep):
        return cadastro_service.definir_ativo(sessao, modelo, identificador, dados.ativo, rotulo)

    return router


clientes = criar_router_cadastro(
    prefixo="/clientes",
    tag="clientes",
    modelo=Cliente,
    entrada=ClienteIn,
    saida=ClienteOut,
    rotulo="cliente",
)
barbeiros = criar_router_cadastro(
    prefixo="/barbeiros",
    tag="barbeiros",
    modelo=Barbeiro,
    entrada=BarbeiroIn,
    saida=BarbeiroOut,
    rotulo="barbeiro",
)
servicos = criar_router_cadastro(
    prefixo="/servicos",
    tag="serviços",
    modelo=Servico,
    entrada=ServicoIn,
    saida=ServicoOut,
    rotulo="serviço",
)
produtos = criar_router_cadastro(
    prefixo="/produtos",
    tag="produtos",
    modelo=Produto,
    entrada=ProdutoIn,
    saida=ProdutoOut,
    rotulo="produto",
)


@clientes.post(
    "/{identificador}/anonimizar",
    response_model=ClienteOut,
    responses={**ERRO_403, **ERRO_404, **ERRO_409},
    summary="Apagar os dados pessoais do cliente (LGPD), mantendo o histórico",
    dependencies=[SomenteDono],
)
def anonimizar_cliente(identificador: int, sessao: SessaoDep, agora: AgoraDep):
    return cadastro_service.anonimizar_cliente(sessao, identificador, agora)
