from datetime import datetime

from fastapi import APIRouter, Query

from app.dependencies import AgoraDep, SessaoDep, SomenteDono
from app.schemas import ERRO_403, ERRO_404, ERRO_409, ERRO_422, VendaIn, VendaOut
from app.services import venda_service

router = APIRouter(prefix="/vendas", tags=["vendas"], dependencies=[SomenteDono])


@router.post(
    "",
    response_model=VendaOut,
    status_code=201,
    responses={**ERRO_403, **ERRO_404, **ERRO_409, **ERRO_422},
    summary="Registrar venda de produtos (baixa o estoque)",
)
def registrar_venda(dados: VendaIn, sessao: SessaoDep, agora: AgoraDep) -> VendaOut:
    return venda_service.registrar(sessao, dados, agora)


@router.get("", response_model=list[VendaOut], summary="Vendas mais recentes")
def listar_vendas(
    sessao: SessaoDep,
    desde: datetime | None = None,
    limite: int = Query(100, ge=1, le=1000),
) -> list[VendaOut]:
    return venda_service.listar(sessao, desde, limite)
