import logging
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
    ConflitoHorarioError,
    DominioError,
    ForaDaDisponibilidadeError,
    HorarioPassadoError,
    RecursoInativoError,
    RecursoNaoEncontradoError,
)
from app.models import Base

PASTA_ESTATICA = Path(__file__).parent / "static"

ERROS_HTTP: dict[type[DominioError], int] = {
    RecursoNaoEncontradoError: 404,
    ConflitoHorarioError: 409,
    ForaDaDisponibilidadeError: 422,
    HorarioPassadoError: 422,
    RecursoInativoError: 422,
}


@asynccontextmanager
async def _preparar_banco(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(engine)
    aplicar_migracoes(engine)
    yield


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
) -> FastAPI:
    logging.basicConfig(level=CONFIG.log_level)
    aplicacao = FastAPI(
        title=titulo, description=descricao, version="2.0.0", lifespan=_preparar_banco
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
