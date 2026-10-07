from fastapi import APIRouter

from app.dependencies import SessaoDep
from app.models import Barbeiro
from app.schemas import ERRO_404, ERRO_422, BarbeiroIn, BarbeiroOut
from app.services import cadastro_service

router = APIRouter(prefix="/barbeiros", tags=["barbeiros"])


@router.post("", response_model=BarbeiroOut, status_code=201, responses=ERRO_422)
def criar_barbeiro(dados: BarbeiroIn, sessao: SessaoDep) -> Barbeiro:
    return cadastro_service.criar(sessao, Barbeiro, dados)


@router.get("", response_model=list[BarbeiroOut])
def listar_barbeiros(sessao: SessaoDep) -> list[Barbeiro]:
    return cadastro_service.listar(sessao, Barbeiro)


@router.get("/{barbeiro_id}", response_model=BarbeiroOut, responses=ERRO_404)
def obter_barbeiro(barbeiro_id: int, sessao: SessaoDep) -> Barbeiro:
    return cadastro_service.obter(sessao, Barbeiro, barbeiro_id, "barbeiro")
