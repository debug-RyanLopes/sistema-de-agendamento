import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import CONFIG
from app.database import engine
from app.errors import (
    ConflitoHorarioError,
    DominioError,
    ForaDaDisponibilidadeError,
    HorarioPassadoError,
    RecursoNaoEncontradoError,
)
from app.models import Base
from app.routers import agendamentos, barbeiros, clientes, disponibilidades, servicos

logging.basicConfig(level=CONFIG.log_level)

PASTA_FRONT_END = Path(__file__).parent / "static"

ERROS_HTTP: dict[type[DominioError], int] = {
    RecursoNaoEncontradoError: 404,
    ConflitoHorarioError: 409,
    ForaDaDisponibilidadeError: 422,
    HorarioPassadoError: 422,
}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(engine)
    yield


def _criar_handler(status: int) -> Callable[[Request, Exception], JSONResponse]:
    def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    return handler


app = FastAPI(
    title="API de Agendamento de Barbearia",
    description="Cadastro de clientes, barbeiros e serviços, disponibilidade e agendamentos "
    "sem conflito de horário, com confirmação simulada por e-mail.",
    version="1.0.0",
    lifespan=lifespan,
)

for tipo_erro, codigo in ERROS_HTTP.items():
    app.add_exception_handler(tipo_erro, _criar_handler(codigo))

for roteador in (clientes, barbeiros, servicos, disponibilidades, agendamentos):
    app.include_router(roteador.router)


@app.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    return RedirectResponse(url="/app/")


app.mount("/app", StaticFiles(directory=PASTA_FRONT_END, html=True), name="front-end")
