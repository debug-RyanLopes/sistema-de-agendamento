from fastapi import APIRouter

from app.dependencies import SessaoDep
from app.models import Servico
from app.schemas import ERRO_404, ERRO_422, ServicoIn, ServicoOut
from app.services import cadastro_service

router = APIRouter(prefix="/servicos", tags=["serviços"])


@router.post("", response_model=ServicoOut, status_code=201, responses=ERRO_422)
def criar_servico(dados: ServicoIn, sessao: SessaoDep) -> Servico:
    return cadastro_service.criar(sessao, Servico, dados)


@router.get("", response_model=list[ServicoOut])
def listar_servicos(sessao: SessaoDep) -> list[Servico]:
    return cadastro_service.listar(sessao, Servico)


@router.get("/{servico_id}", response_model=ServicoOut, responses=ERRO_404)
def obter_servico(servico_id: int, sessao: SessaoDep) -> Servico:
    return cadastro_service.obter(sessao, Servico, servico_id, "serviço")
