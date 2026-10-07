from datetime import date

from fastapi import APIRouter

from app.config import CONFIG
from app.dependencies import AgoraDep, SessaoDep
from app.models import Disponibilidade
from app.schemas import (
    ERRO_404,
    ERRO_422,
    DisponibilidadeIn,
    DisponibilidadeOut,
    HorariosLivresOut,
)
from app.services import disponibilidade_service

router = APIRouter(prefix="/barbeiros/{barbeiro_id}", tags=["disponibilidade"])


@router.post(
    "/disponibilidades",
    response_model=DisponibilidadeOut,
    status_code=201,
    responses={**ERRO_404, **ERRO_422},
)
def cadastrar_disponibilidade(
    barbeiro_id: int, dados: DisponibilidadeIn, sessao: SessaoDep
) -> Disponibilidade:
    return disponibilidade_service.cadastrar_janela(sessao, barbeiro_id, dados)


@router.get(
    "/disponibilidades", response_model=list[DisponibilidadeOut], responses=ERRO_404
)
def listar_disponibilidades(barbeiro_id: int, sessao: SessaoDep) -> list[Disponibilidade]:
    return disponibilidade_service.listar_janelas(sessao, barbeiro_id)


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
