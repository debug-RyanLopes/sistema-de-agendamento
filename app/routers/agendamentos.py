from datetime import date

from fastapi import APIRouter, BackgroundTasks, Query

from app.dependencies import AgoraDep, NotificadorDep, SessaoDep
from app.models import Agendamento, StatusAgendamento
from app.schemas import (
    ERRO_404,
    ERRO_409,
    ERRO_422,
    AgendamentoIn,
    AgendamentoOut,
    PaginaAgendamentosOut,
)
from app.services import agendamento_service
from app.services.notificacao_service import enviar_sem_falhar

router = APIRouter(prefix="/agendamentos", tags=["agendamentos"])


@router.post(
    "",
    response_model=AgendamentoOut,
    status_code=201,
    responses={**ERRO_404, **ERRO_409, **ERRO_422},
)
def criar_agendamento(
    dados: AgendamentoIn,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    agora: AgoraDep,
    notificador: NotificadorDep,
) -> Agendamento:
    agendamento, confirmacao = agendamento_service.criar(sessao, dados, agora)
    tarefas.add_task(enviar_sem_falhar, notificador, confirmacao)
    return agendamento


LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200


@router.get(
    "",
    response_model=PaginaAgendamentosOut,
    summary="Listar agendamentos (paginado)",
    description=(
        f"Devolve no máximo `limite` itens por chamada (padrão {LIMITE_PADRAO}, "
        f"máximo {LIMITE_MAXIMO}), ordenados por início, mais o `total` que atende aos filtros. "
        "Use `desde` para ver só de uma data em diante."
    ),
)
def listar_agendamentos(
    sessao: SessaoDep,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    data: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
    limite: int = Query(LIMITE_PADRAO, ge=1, le=LIMITE_MAXIMO),
    deslocamento: int = Query(0, ge=0, le=1_000_000),
) -> PaginaAgendamentosOut:
    itens, total = agendamento_service.pagina(
        sessao, limite, deslocamento, barbeiro_id, cliente_id, data, status, desde
    )
    return PaginaAgendamentosOut(
        itens=itens, total=total, limite=limite, deslocamento=deslocamento
    )


@router.get("/{agendamento_id}", response_model=AgendamentoOut, responses=ERRO_404)
def obter_agendamento(agendamento_id: int, sessao: SessaoDep) -> Agendamento:
    return agendamento_service.obter(sessao, agendamento_id)


@router.delete("/{agendamento_id}", response_model=AgendamentoOut, responses=ERRO_404)
def cancelar_agendamento(agendamento_id: int, sessao: SessaoDep) -> Agendamento:
    return agendamento_service.cancelar(sessao, agendamento_id)
