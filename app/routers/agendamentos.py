from datetime import date

from fastapi import APIRouter, BackgroundTasks, Query

from app.dependencies import AgoraDep, NotificadorDep, SessaoDep, UsuarioDep
from app.errors import AcessoNegadoError
from app.models import Agendamento, StatusAgendamento
from app.schemas import (
    ERRO_403,
    ERRO_404,
    ERRO_409,
    ERRO_422,
    AgendamentoIn,
    AgendamentoOut,
    PaginaAgendamentosOut,
    ReagendamentoIn,
    StatusIn,
)
from app.services import agendamento_service
from app.services.auth_service import UsuarioAutenticado
from app.services.notificacao_service import notificar_sem_falhar

router = APIRouter(prefix="/agendamentos", tags=["agendamentos"])

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200


def _escopo(usuario: UsuarioAutenticado, barbeiro_id: int | None) -> int | None:
    """Barbeiro só enxerga a própria agenda; o dono escolhe o filtro."""
    if usuario.e_dono:
        return barbeiro_id
    if barbeiro_id not in (None, usuario.barbeiro_id):
        raise AcessoNegadoError("você só pode ver a própria agenda")
    return usuario.barbeiro_id


def _saida(sessao, agendamento: Agendamento) -> AgendamentoOut:
    resumo = agendamento_service.resumo_dos_servicos(sessao, agendamento)
    saida = AgendamentoOut.model_validate(agendamento)
    saida.servico_ids = resumo.ids
    saida.preco = resumo.preco
    return saida


def _saidas(sessao, itens: list[Agendamento]) -> list[AgendamentoOut]:
    """Mesma coisa para uma página inteira, com uma única consulta aos serviços."""
    combos = agendamento_service.servicos_de_varios(sessao, itens)
    saidas = []
    for agendamento in itens:
        saida = AgendamentoOut.model_validate(agendamento)
        saida.servico_ids, saida.preco = combos[agendamento.id]
        saidas.append(saida)
    return saidas


def _somente_do(usuario: UsuarioAutenticado) -> int | None:
    """Restrição passada aos serviços: barbeiro só mexe nos próprios agendamentos."""
    return None if usuario.e_dono else usuario.barbeiro_id


@router.post(
    "",
    response_model=AgendamentoOut,
    status_code=201,
    responses={**ERRO_403, **ERRO_404, **ERRO_409, **ERRO_422},
)
def criar_agendamento(
    dados: AgendamentoIn,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    agora: AgoraDep,
    notificador: NotificadorDep,
    usuario: UsuarioDep,
) -> AgendamentoOut:
    _escopo(usuario, dados.barbeiro_id)
    agendamento, confirmacao = agendamento_service.criar(sessao, dados, agora)
    tarefas.add_task(notificar_sem_falhar, notificador, "enviar_confirmacao", confirmacao)
    return _saida(sessao, agendamento)


@router.get(
    "",
    response_model=PaginaAgendamentosOut,
    summary="Listar agendamentos (paginado)",
    description=(
        f"Devolve no máximo `limite` itens por chamada (padrão {LIMITE_PADRAO}, "
        f"máximo {LIMITE_MAXIMO}), ordenados por início, mais o `total` que atende aos filtros. "
        "Use `desde` e `ate` para delimitar o período. Usuário com papel barbeiro vê só a "
        "própria agenda."
    ),
)
def listar_agendamentos(
    sessao: SessaoDep,
    usuario: UsuarioDep,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    data: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
    ate: date | None = None,
    limite: int = Query(LIMITE_PADRAO, ge=1, le=LIMITE_MAXIMO),
    deslocamento: int = Query(0, ge=0, le=1_000_000),
) -> PaginaAgendamentosOut:
    itens, total = agendamento_service.pagina(
        sessao,
        limite,
        deslocamento,
        _escopo(usuario, barbeiro_id),
        cliente_id,
        data,
        status,
        desde,
        ate,
    )
    return PaginaAgendamentosOut(
        itens=_saidas(sessao, itens), total=total, limite=limite, deslocamento=deslocamento
    )


@router.get("/{agendamento_id}", response_model=AgendamentoOut, responses={**ERRO_403, **ERRO_404})
def obter_agendamento(
    agendamento_id: int, sessao: SessaoDep, usuario: UsuarioDep
) -> AgendamentoOut:
    return _saida(
        sessao, agendamento_service.obter_para(sessao, agendamento_id, _somente_do(usuario))
    )


@router.delete(
    "/{agendamento_id}",
    response_model=AgendamentoOut,
    responses={**ERRO_403, **ERRO_404, **ERRO_409, **ERRO_422},
    summary="Cancelar agendamento futuro",
    description="Horário que já passou não se cancela: use PATCH .../status para concluir "
    "ou registrar falta. O cliente recebe o aviso de cancelamento.",
)
def cancelar_agendamento(
    agendamento_id: int,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    agora: AgoraDep,
    notificador: NotificadorDep,
    usuario: UsuarioDep,
    motivo: str | None = Query(None, max_length=200),
) -> AgendamentoOut:
    agendamento, cancelou = agendamento_service.cancelar(
        sessao, agendamento_id, agora, motivo=motivo, somente_do_barbeiro=_somente_do(usuario)
    )
    if cancelou:
        dados = agendamento_service.dados_para_notificacao(sessao, agendamento)
        tarefas.add_task(notificar_sem_falhar, notificador, "enviar_cancelamento", dados)
    return _saida(sessao, agendamento)


@router.patch(
    "/{agendamento_id}/status",
    response_model=AgendamentoOut,
    responses={**ERRO_403, **ERRO_404, **ERRO_409, **ERRO_422},
    summary="Encerrar atendimento passado como concluído ou falta",
)
def marcar_status(
    agendamento_id: int, dados: StatusIn, sessao: SessaoDep, agora: AgoraDep, usuario: UsuarioDep
) -> AgendamentoOut:
    return _saida(
        sessao,
        agendamento_service.marcar_status(
            sessao, agendamento_id, dados.status, agora, _somente_do(usuario)
        ),
    )


@router.post(
    "/{agendamento_id}/reagendar",
    response_model=AgendamentoOut,
    responses={**ERRO_403, **ERRO_404, **ERRO_409, **ERRO_422},
    summary="Remarcar para outro horário com o mesmo barbeiro e serviço",
)
def reagendar(
    agendamento_id: int,
    dados: ReagendamentoIn,
    tarefas: BackgroundTasks,
    sessao: SessaoDep,
    agora: AgoraDep,
    notificador: NotificadorDep,
    usuario: UsuarioDep,
) -> AgendamentoOut:
    agendamento, confirmacao = agendamento_service.reagendar(
        sessao, agendamento_id, dados.inicio, agora, somente_do_barbeiro=_somente_do(usuario)
    )
    tarefas.add_task(notificar_sem_falhar, notificador, "enviar_confirmacao", confirmacao)
    return _saida(sessao, agendamento)
