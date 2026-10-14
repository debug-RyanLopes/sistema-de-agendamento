from datetime import date

from fastapi import APIRouter, BackgroundTasks

from app.config import CONFIG
from app.dependencies import AgoraDep, NotificadorDep, SessaoDep
from app.models import Servico
from app.schemas import (
    ERRO_404,
    ERRO_409,
    ERRO_422,
    AgendamentoPublicoIn,
    BarbeiroDisponivelOut,
    CancelamentoIn,
    CancelamentoOut,
    ConfirmacaoOut,
    DisponibilidadeDiaOut,
    ServicoPublicoOut,
)
from app.services import agendamento_service, cadastro_service, disponibilidade_service
from app.services.notificacao_service import enviar_sem_falhar

router = APIRouter(tags=["cliente"])


@router.get("/servicos", response_model=list[ServicoPublicoOut], summary="Serviços disponíveis")
def listar_servicos(sessao: SessaoDep) -> list[Servico]:
    return cadastro_service.listar(sessao, Servico)


@router.get(
    "/disponibilidade",
    response_model=DisponibilidadeDiaOut,
    responses={**ERRO_404, **ERRO_422},
    summary="Barbeiros com horários livres no dia",
)
def disponibilidade(
    data: date, servico_id: int, sessao: SessaoDep, agora: AgoraDep
) -> DisponibilidadeDiaOut:
    disponiveis = disponibilidade_service.barbeiros_disponiveis(
        sessao, servico_id, data, agora, CONFIG.slot_minutes
    )
    return DisponibilidadeDiaOut(
        data=data,
        servico_id=servico_id,
        barbeiros=[
            BarbeiroDisponivelOut(id=barbeiro.id, nome=barbeiro.nome, horarios=horarios)
            for barbeiro, horarios in disponiveis
        ],
    )


@router.post(
    "/agendamentos",
    response_model=ConfirmacaoOut,
    status_code=201,
    responses={**ERRO_404, **ERRO_409, **ERRO_422},
    summary="Marcar agendamento",
)
def agendar(
    dados: AgendamentoPublicoIn,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    agora: AgoraDep,
    notificador: NotificadorDep,
) -> ConfirmacaoOut:
    agendamento, confirmacao = agendamento_service.criar_publico(sessao, dados, agora)
    tarefas.add_task(enviar_sem_falhar, notificador, confirmacao)
    return ConfirmacaoOut(
        id=agendamento.id,
        codigo_cancelamento=agendamento.codigo_cancelamento,
        barbeiro=confirmacao.barbeiro,
        servico=confirmacao.servico,
        inicio=agendamento.inicio,
        fim=agendamento.fim,
        preco=confirmacao.preco,
        status=agendamento.status,
    )


@router.post(
    "/agendamentos/{agendamento_id}/cancelar",
    response_model=CancelamentoOut,
    responses={**ERRO_404, **ERRO_422},
    summary="Cancelar o próprio agendamento com o código",
)
def cancelar(
    agendamento_id: int, dados: CancelamentoIn, sessao: SessaoDep, agora: AgoraDep
) -> CancelamentoOut:
    agendamento = agendamento_service.cancelar_com_codigo(
        sessao, agendamento_id, dados.codigo, agora
    )
    return CancelamentoOut(id=agendamento.id, status=agendamento.status)
