from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Response
from fastapi.exceptions import RequestValidationError

from app.calendario import gerar_ics
from app.config import CONFIG
from app.dependencies import AgoraDep, ChaveDep, NotificadorDep, SessaoDep
from app.errors import RecursoNaoEncontradoError, TransicaoInvalidaError
from app.models import Servico
from app.repositories import agendamentos as repositorio_agendamentos
from app.repositories import cadastros
from app.schemas import (
    ERRO_404,
    ERRO_409,
    ERRO_422,
    ERRO_429,
    MAXIMO_SERVICOS,
    AgendamentoPublicoIn,
    BarbeiroDisponivelOut,
    CancelamentoIn,
    CancelamentoOut,
    ConfirmacaoOut,
    DisponibilidadeDiaOut,
    MeuAgendamentoOut,
    MeusAgendamentosOut,
    ReagendamentoPublicoIn,
    ServicoPublicoOut,
    SolicitacaoLinkIn,
)
from app.services import (
    agendamento_service,
    auth_service,
    cadastro_service,
    disponibilidade_service,
)
from app.services.notificacao_service import DadosAgendamento, notificar_sem_falhar

SEM_SERVICO = "informe servico_id ou servico_ids"

router = APIRouter(tags=["cliente"])

FINALIDADE_LINK = "meus-agendamentos"
VALIDADE_LINK_SEGUNDOS = 30 * 60


def _confirmacao(sessao, agendamento, dados: DadosAgendamento) -> ConfirmacaoOut:
    resumo = agendamento_service.resumo_dos_servicos(sessao, agendamento)
    return ConfirmacaoOut(
        id=agendamento.id,
        codigo_cancelamento=agendamento.codigo_cancelamento,
        barbeiro=dados.barbeiro,
        servico=dados.servico,
        servicos=resumo.nomes,
        servico_ids=resumo.ids,
        duracao_minutos=resumo.duracao_minutos,
        inicio=agendamento.inicio,
        fim=agendamento.fim,
        preco=dados.preco,
        status=agendamento.status,
    )


def _ids(servico_id: int | None, servico_ids: list[int] | None) -> list[int]:
    ids = list(servico_ids or [])
    if servico_id is not None and servico_id not in ids:
        ids.insert(0, servico_id)
    if not ids:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "servico_ids"),
                    "msg": "informe servico_id ou servico_ids",
                    "type": "missing",
                }
            ]
        )
    return list(dict.fromkeys(ids))


@router.get("/servicos", response_model=list[ServicoPublicoOut], summary="Serviços disponíveis")
def listar_servicos(sessao: SessaoDep) -> list[Servico]:
    return cadastro_service.listar(sessao, Servico)


@router.get(
    "/disponibilidade",
    response_model=DisponibilidadeDiaOut,
    responses={**ERRO_404, **ERRO_422},
    summary="Barbeiros com horários livres no dia",
    description="Use `servico_id` para um serviço ou `servico_ids` (repetido) para um combo; "
    "os horários avançam pela duração total e cada opção comporta todos os serviços.",
)
def disponibilidade(
    data: date,
    sessao: SessaoDep,
    agora: AgoraDep,
    servico_id: int | None = None,
    servico_ids: Annotated[list[int] | None, Query(max_length=MAXIMO_SERVICOS)] = None,
) -> DisponibilidadeDiaOut:
    ids = _ids(servico_id, servico_ids)
    servicos = disponibilidade_service.servicos_escolhidos(sessao, ids)
    disponiveis = disponibilidade_service.barbeiros_disponiveis(
        sessao, ids, data, agora, CONFIG.slot_minutes
    )
    return DisponibilidadeDiaOut(
        data=data,
        servico_id=ids[0],
        servico_ids=ids,
        duracao_minutos=disponibilidade_service.duracao_total(servicos),
        preco=sum(servico.preco for servico in servicos),
        barbeiros=[
            BarbeiroDisponivelOut(id=barbeiro.id, nome=barbeiro.nome, horarios=horarios)
            for barbeiro, horarios in disponiveis
        ],
    )


@router.post(
    "/agendamentos",
    response_model=ConfirmacaoOut,
    status_code=201,
    responses={**ERRO_404, **ERRO_409, **ERRO_422, **ERRO_429},
    summary="Marcar agendamento",
    description="Sem `barbeiro_id`, escolhe o barbeiro com o horário livre e menos agenda no dia.",
)
def agendar(
    dados: AgendamentoPublicoIn,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    agora: AgoraDep,
    notificador: NotificadorDep,
) -> ConfirmacaoOut:
    agendamento, confirmacao = agendamento_service.criar_publico(sessao, dados, agora)
    tarefas.add_task(notificar_sem_falhar, notificador, "enviar_confirmacao", confirmacao)
    return _confirmacao(sessao, agendamento, confirmacao)


@router.post(
    "/agendamentos/{agendamento_id}/cancelar",
    response_model=CancelamentoOut,
    responses={**ERRO_404, **ERRO_422, **ERRO_429},
    summary="Cancelar o próprio agendamento com o código",
)
def cancelar(
    agendamento_id: int,
    dados: CancelamentoIn,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    agora: AgoraDep,
    notificador: NotificadorDep,
) -> CancelamentoOut:
    agendamento, cancelou = agendamento_service.cancelar_com_codigo(
        sessao, agendamento_id, dados.codigo, agora
    )
    if cancelou:
        aviso = agendamento_service.dados_para_notificacao(sessao, agendamento)
        tarefas.add_task(notificar_sem_falhar, notificador, "enviar_cancelamento", aviso)
    return CancelamentoOut(id=agendamento.id, status=agendamento.status)


@router.post(
    "/agendamentos/{agendamento_id}/reagendar",
    response_model=ConfirmacaoOut,
    responses={**ERRO_404, **ERRO_409, **ERRO_422, **ERRO_429},
    summary="Remarcar o próprio agendamento com o código",
)
def reagendar(
    agendamento_id: int,
    dados: ReagendamentoPublicoIn,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    agora: AgoraDep,
    notificador: NotificadorDep,
) -> ConfirmacaoOut:
    agendamento, confirmacao = agendamento_service.reagendar_com_codigo(
        sessao, agendamento_id, dados.codigo, dados.inicio, agora
    )
    tarefas.add_task(notificar_sem_falhar, notificador, "enviar_confirmacao", confirmacao)
    return _confirmacao(sessao, agendamento, confirmacao)


@router.get(
    "/agendamentos/{agendamento_id}/ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}, **ERRO_404},
    summary="Baixar o agendamento como evento de calendário (.ics)",
)
def baixar_ics(
    agendamento_id: int, sessao: SessaoDep, agora: AgoraDep, codigo: str = Query(max_length=64)
) -> Response:
    agendamento = agendamento_service.obter_com_codigo(sessao, agendamento_id, codigo)
    dados = agendamento_service.dados_para_notificacao(sessao, agendamento)
    return Response(
        gerar_ics(dados, agendamento.fim, CONFIG.timezone, agora),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="agendamento-{agendamento.id}.ics"'
        },
    )


@router.post(
    "/meus-agendamentos/solicitar",
    status_code=202,
    responses=ERRO_429,
    summary="Receber por e-mail um link para ver e cancelar os próprios agendamentos",
    description="Responde 202 sempre, exista ou não o e-mail, para não revelar cadastros.",
)
def solicitar_link(
    dados: SolicitacaoLinkIn,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    notificador: NotificadorDep,
    chave: ChaveDep,
) -> dict[str, str]:
    if cadastros.obter_cliente_por_email(sessao, dados.email) is not None:
        token = auth_service.gerar_token(
            chave, FINALIDADE_LINK, dados.email, VALIDADE_LINK_SEGUNDOS
        )
        url = f"{CONFIG.url_publica}/?token={token}"
        tarefas.add_task(
            notificar_sem_falhar, notificador, "enviar_link", dados.email, "Seus agendamentos", url
        )
    return {"detail": "se o e-mail estiver cadastrado, o link chega em instantes"}


def _email_do_token(chave: str, token: str) -> str:
    email = auth_service.ler_token(chave, FINALIDADE_LINK, token)
    if email is None:
        raise RecursoNaoEncontradoError("link inválido ou expirado; peça outro")
    return email


@router.get(
    "/meus-agendamentos",
    response_model=MeusAgendamentosOut,
    responses=ERRO_404,
    summary="Agendamentos futuros do cliente do link",
)
def meus_agendamentos(
    sessao: SessaoDep, agora: AgoraDep, chave: ChaveDep, token: str = Query(max_length=400)
) -> MeusAgendamentosOut:
    email = _email_do_token(chave, token)
    return MeusAgendamentosOut(
        email=email,
        agendamentos=[
            MeuAgendamentoOut(
                id=agendamento.id,
                codigo_cancelamento=agendamento.codigo_cancelamento,
                barbeiro=barbeiro,
                servico=servico,
                servico_ids=agendamento_service.resumo_dos_servicos(sessao, agendamento).ids,
                inicio=agendamento.inicio,
                fim=agendamento.fim,
                status=agendamento.status,
            )
            for agendamento, barbeiro, servico in agendamento_service.meus_agendamentos(
                sessao, email, agora
            )
        ],
    )


@router.post(
    "/meus-dados/exclusao",
    status_code=204,
    responses={**ERRO_404, **ERRO_409},
    summary="Apagar os próprios dados pessoais (LGPD) usando o link recebido",
)
def excluir_meus_dados(
    sessao: SessaoDep, agora: AgoraDep, chave: ChaveDep, token: str = Query(max_length=400)
) -> Response:
    email = _email_do_token(chave, token)
    cliente = cadastros.obter_cliente_por_email(sessao, email)
    if cliente is None:
        raise RecursoNaoEncontradoError("cadastro não encontrado")
    if repositorio_agendamentos.contar_ativos_do_cliente(sessao, cliente.id, agora):
        raise TransicaoInvalidaError("cancele seus agendamentos futuros antes de apagar os dados")
    cadastro_service.anonimizar_cliente(sessao, cliente.id, agora)
    return Response(status_code=204)
