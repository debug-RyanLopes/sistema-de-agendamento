from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response
from fastapi.exceptions import RequestValidationError

from app.config import CONFIG
from app.dependencies import AgoraDep, SessaoDep, SomenteDono
from app.models import Bloqueio, Disponibilidade, Servico
from app.schemas import (
    ERRO_403,
    ERRO_404,
    ERRO_422,
    MAXIMO_SERVICOS,
    BloqueioIn,
    BloqueioOut,
    DisponibilidadeIn,
    DisponibilidadeOut,
    HorariosLivresOut,
)
from app.services import cadastro_service, disponibilidade_service

SEM_SERVICO = "informe servico_id ou servico_ids"

router = APIRouter(prefix="/barbeiros/{barbeiro_id}", tags=["disponibilidade"])
bloqueios = APIRouter(prefix="/bloqueios", tags=["disponibilidade"])


@router.post(
    "/disponibilidades",
    response_model=DisponibilidadeOut,
    status_code=201,
    responses={**ERRO_403, **ERRO_404, **ERRO_422},
    dependencies=[SomenteDono],
)
def cadastrar_disponibilidade(
    barbeiro_id: int, dados: DisponibilidadeIn, sessao: SessaoDep
) -> Disponibilidade:
    return disponibilidade_service.cadastrar_janela(sessao, barbeiro_id, dados)


@router.get("/disponibilidades", response_model=list[DisponibilidadeOut], responses=ERRO_404)
def listar_disponibilidades(barbeiro_id: int, sessao: SessaoDep) -> list[Disponibilidade]:
    return disponibilidade_service.listar_janelas(sessao, barbeiro_id)


@router.delete(
    "/disponibilidades/{janela_id}",
    status_code=204,
    responses={**ERRO_403, **ERRO_404},
    dependencies=[SomenteDono],
)
def remover_disponibilidade(barbeiro_id: int, janela_id: int, sessao: SessaoDep) -> Response:
    disponibilidade_service.remover_janela(sessao, barbeiro_id, janela_id)
    return Response(status_code=204)


@router.get(
    "/horarios-livres",
    response_model=HorariosLivresOut,
    responses={**ERRO_404, **ERRO_422},
)
def horarios_livres(
    barbeiro_id: int,
    data: date,
    sessao: SessaoDep,
    agora: AgoraDep,
    servico_id: int | None = None,
    servico_ids: Annotated[list[int] | None, Query(max_length=MAXIMO_SERVICOS)] = None,
) -> HorariosLivresOut:
    ids = list(
        dict.fromkeys(([servico_id] if servico_id is not None else []) + (servico_ids or []))
    )
    if not ids:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "servico_id"),
                    "msg": "informe servico_id ou servico_ids",
                    "type": "missing",
                }
            ]
        )
    horarios = disponibilidade_service.horarios_livres(
        sessao, barbeiro_id, ids, data, agora, CONFIG.slot_minutes
    )
    duracao = disponibilidade_service.duracao_total(
        [cadastro_service.obter(sessao, Servico, item, "serviço") for item in ids]
    )
    return HorariosLivresOut(
        barbeiro_id=barbeiro_id,
        servico_id=ids[0],
        servico_ids=ids,
        duracao_minutos=duracao,
        data=data,
        horarios=horarios,
    )


@bloqueios.post(
    "",
    response_model=BloqueioOut,
    status_code=201,
    responses={**ERRO_403, **ERRO_404, **ERRO_422},
    summary="Folga, feriado ou bloqueio pontual",
    dependencies=[SomenteDono],
)
def criar_bloqueio(dados: BloqueioIn, sessao: SessaoDep) -> Bloqueio:
    return disponibilidade_service.criar_bloqueio(sessao, dados)


@bloqueios.get("", response_model=list[BloqueioOut], summary="Listar bloqueios")
def listar_bloqueios(
    sessao: SessaoDep, desde: date | None = None, barbeiro_id: int | None = None
) -> list[Bloqueio]:
    return disponibilidade_service.listar_bloqueios(sessao, desde, barbeiro_id)


@bloqueios.delete(
    "/{bloqueio_id}",
    status_code=204,
    responses={**ERRO_403, **ERRO_404},
    dependencies=[SomenteDono],
)
def remover_bloqueio(bloqueio_id: int, sessao: SessaoDep) -> Response:
    disponibilidade_service.remover_bloqueio(sessao, bloqueio_id)
    return Response(status_code=204)
