from datetime import date

from fastapi import APIRouter, Response

from app.dependencies import SessaoDep, SomenteDono, UsuarioDep
from app.errors import AcessoNegadoError
from app.models import StatusAgendamento
from app.schemas import ERRO_403, ERRO_422, ResumoOut
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["relatórios"])


@router.get(
    "/resumo",
    response_model=ResumoOut,
    responses={**ERRO_403, **ERRO_422},
    summary="Ocupação e receita por barbeiro no período",
    dependencies=[SomenteDono],
)
def resumo(desde: date, ate: date, sessao: SessaoDep) -> ResumoOut:
    return relatorio_service.resumo(sessao, desde, ate)


@router.get(
    "/agendamentos.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}, **ERRO_403},
    summary="Exportar agendamentos em CSV (mesmos filtros da listagem)",
)
def exportar_csv(
    sessao: SessaoDep,
    usuario: UsuarioDep,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    data: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
    ate: date | None = None,
) -> Response:
    if not usuario.e_dono:
        if barbeiro_id not in (None, usuario.barbeiro_id):
            raise AcessoNegadoError("você só pode exportar a própria agenda")
        barbeiro_id = usuario.barbeiro_id
    conteudo = relatorio_service.agendamentos_csv(
        sessao, barbeiro_id, cliente_id, data, status, desde, ate
    )
    return Response(
        "\ufeff" + conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="agendamentos.csv"'},
    )
