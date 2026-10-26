from datetime import date

from fastapi import APIRouter, Response

from app.config import CONFIG
from app.dependencies import AgoraDep, SessaoDep, SomenteDono
from app.models import Bloqueio, Disponibilidade
from app.schemas import (
    ERRO_403,
    ERRO_404,
    ERRO_422,
    BloqueioIn,
    BloqueioOut,
    DisponibilidadeIn,
    DisponibilidadeOut,
    HorariosLivresOut,
)
from app.services import disponibilidade_service

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
    barbeiro_id: int, data: date, servico_id: int, sessao: SessaoDep, agora: AgoraDep
) -> HorariosLivresOut:
    horarios = disponibilidade_service.horarios_livres(
        sessao, barbeiro_id, servico_id, data, agora, CONFIG.slot_minutes
    )
    return HorariosLivresOut(
        barbeiro_id=barbeiro_id, servico_id=servico_id, data=data, horarios=horarios
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
