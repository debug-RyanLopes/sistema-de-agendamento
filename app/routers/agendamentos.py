from datetime import date

from fastapi import APIRouter, BackgroundTasks

from app.dependencies import AgoraDep, NotificadorDep, SessaoDep
from app.models import Agendamento, StatusAgendamento
from app.schemas import ERRO_404, ERRO_409, ERRO_422, AgendamentoIn, AgendamentoOut
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


@router.get("", response_model=list[AgendamentoOut])
def listar_agendamentos(
    sessao: SessaoDep,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    data: date | None = None,
    status: StatusAgendamento | None = None,
) -> list[Agendamento]:
    return agendamento_service.listar(sessao, barbeiro_id, cliente_id, data, status)


@router.get("/{agendamento_id}", response_model=AgendamentoOut, responses=ERRO_404)
def obter_agendamento(agendamento_id: int, sessao: SessaoDep) -> Agendamento:
    return agendamento_service.obter(sessao, agendamento_id)


@router.delete("/{agendamento_id}", response_model=AgendamentoOut, responses=ERRO_404)
def cancelar_agendamento(agendamento_id: int, sessao: SessaoDep) -> Agendamento:
    return agendamento_service.cancelar(sessao, agendamento_id)
