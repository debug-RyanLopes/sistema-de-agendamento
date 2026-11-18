from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import CONFIG
from app.database import aplicar_migracoes, engine
from app.errors import (
    AcessoNegadoError,
    ConflitoHorarioError,
    DataForaDaJanelaError,
    DominioError,
    EstoqueInsuficienteError,
    ForaDaDisponibilidadeError,
    HorarioInvalidoError,
    HorarioPassadoError,
    LimiteExcedidoError,
    NaoAutorizadoError,
    RecursoDuplicadoError,
    RecursoInativoError,
    RecursoNaoEncontradoError,
    TransicaoInvalidaError,
)
from app.logs import configurar_logging
from app.models import Base
from app.routers.sistema import VERSAO

PASTA_ESTATICA = Path(__file__).parent / "static"

ERROS_HTTP: dict[type[DominioError], int] = {
    NaoAutorizadoError: 401,
    AcessoNegadoError: 403,
    RecursoNaoEncontradoError: 404,
    ConflitoHorarioError: 409,
    RecursoDuplicadoError: 409,
    TransicaoInvalidaError: 409,
    EstoqueInsuficienteError: 409,
    ForaDaDisponibilidadeError: 422,
    HorarioPassadoError: 422,
    RecursoInativoError: 422,
    HorarioInvalidoError: 422,
    DataForaDaJanelaError: 422,
    LimiteExcedidoError: 422,
}

# Cada inicializador roda depois do banco estar pronto e devolve a função que o encerra.
Inicializador = Callable[[], Callable[[], None]]


def _criar_handler(status: int) -> Callable[[Request, Exception], JSONResponse]:
    def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    return handler


def criar_aplicacao(
    *,
    titulo: str,
    descricao: str,
    routers: Sequence[APIRouter],
    pasta_front_end: str,
    middlewares: Sequence[tuple[type, dict[str, Any]]] = (),
    inicializadores: Sequence[Inicializador] = (),
) -> FastAPI:
    configurar_logging(CONFIG.log_level, CONFIG.log_json)

    @asynccontextmanager
    async def _ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        aplicar_migracoes(engine)
        encerradores = [iniciar() for iniciar in inicializadores]
        try:
            yield
        finally:
            for encerrar in reversed(encerradores):
                encerrar()

    aplicacao = FastAPI(
        title=titulo, description=descricao, version=VERSAO, lifespan=_ciclo_de_vida
    )
    for tipo_erro, codigo in ERROS_HTTP.items():
        aplicacao.add_exception_handler(tipo_erro, _criar_handler(codigo))
    for roteador in routers:
        aplicacao.include_router(roteador)
    aplicacao.mount(
        "/comum", StaticFiles(directory=PASTA_ESTATICA / "comum"), name="estaticos-comuns"
    )
    aplicacao.mount(
        "/",
        StaticFiles(directory=PASTA_ESTATICA / pasta_front_end, html=True),
        name="front-end",
    )
    for classe, opcoes in middlewares:
        aplicacao.add_middleware(classe, **opcoes)
    return aplicacao
