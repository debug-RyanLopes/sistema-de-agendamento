from fastapi import APIRouter

from app.dependencies import AgoraDep, SessaoDep, SomenteDono
from app.schemas import ERRO_403, ERRO_404, ImpactoDesativacaoOut
from app.services import barbeiro_service

router = APIRouter(prefix="/barbeiros", tags=["barbeiros"])


@router.get(
    "/{barbeiro_id}/impacto-desativacao",
    response_model=ImpactoDesativacaoOut,
    responses={**ERRO_403, **ERRO_404},
    summary="Resumo do que muda ao desativar o barbeiro",
    dependencies=[SomenteDono],
)
def impacto_desativacao(
    barbeiro_id: int, sessao: SessaoDep, agora: AgoraDep
) -> ImpactoDesativacaoOut:
    return barbeiro_service.impacto_desativacao(sessao, barbeiro_id, agora)
