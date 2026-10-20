import secrets
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import CONFIG
from app.errors import (
    ConflitoHorarioError,
    DominioError,
    ForaDaDisponibilidadeError,
    HorarioInvalidoError,
    HorarioPassadoError,
    RecursoInativoError,
    RecursoNaoEncontradoError,
)
from app.models import Agendamento, Barbeiro, Cliente, Servico, StatusAgendamento
from app.repositories import agendamentos, cadastros, disponibilidades
from app.schemas import AgendamentoIn, AgendamentoPublicoIn
from app.services import cadastro_service, disponibilidade_service
from app.services.notificacao_service import DadosConfirmacao

TAMANHO_CODIGO_BYTES = 8


def _validar_e_gravar(
    session: Session,
    cliente: Cliente,
    barbeiro: Barbeiro,
    servico: Servico,
    inicio: datetime,
    agora: datetime,
    codigo_cancelamento: str | None,
    slot_minutos: int | None = None,
) -> tuple[Agendamento, DadosConfirmacao]:
    fim = inicio + timedelta(minutes=servico.duracao_minutos)

    if inicio <= agora:
        raise HorarioPassadoError("o horário escolhido já passou")
    if not disponibilidade_service.horario_alinhado(inicio, slot_minutos):
        raise HorarioInvalidoError(
            "o horário deve começar em múltiplos de "
            f"{slot_minutos or CONFIG.slot_minutes} minutos (ex.: 10:00, 10:30)"
        )
    if not disponibilidades.cobre(session, barbeiro.id, inicio, fim):
        raise ForaDaDisponibilidadeError("o horário está fora da disponibilidade do barbeiro")
    if agendamentos.existe_sobreposicao(session, barbeiro.id, inicio, fim):
        raise ConflitoHorarioError("o barbeiro já tem um agendamento nesse horário")

    agendamento = agendamentos.adicionar(
        session,
        Agendamento(
            cliente_id=cliente.id,
            barbeiro_id=barbeiro.id,
            servico_id=servico.id,
            inicio=inicio,
            fim=fim,
            status=StatusAgendamento.AGENDADO,
            codigo_cancelamento=codigo_cancelamento,
        ),
    )
    session.commit()
    confirmacao = DadosConfirmacao(
        email=cliente.email,
        cliente=cliente.nome,
        barbeiro=barbeiro.nome,
        servico=servico.nome,
        inicio=inicio,
        preco=servico.preco,
    )
    return agendamento, confirmacao


def criar(
    session: Session, dados: AgendamentoIn, agora: datetime, slot_minutos: int | None = None
) -> tuple[Agendamento, DadosConfirmacao]:
    cliente = cadastro_service.obter_ativo(session, Cliente, dados.cliente_id, "cliente")
    barbeiro = cadastro_service.obter_ativo(session, Barbeiro, dados.barbeiro_id, "barbeiro")
    servico = cadastro_service.obter_ativo(session, Servico, dados.servico_id, "serviço")
    return _validar_e_gravar(
        session, cliente, barbeiro, servico, dados.inicio, agora, None, slot_minutos
    )


def _obter_ou_criar_cliente(session: Session, dados: AgendamentoPublicoIn) -> Cliente:
    existente = cadastros.obter_cliente_por_email(session, dados.email)
    if existente is None:
        return cadastros.adicionar(
            session, Cliente(nome=dados.nome, email=dados.email, telefone=dados.telefone)
        )
    if not existente.ativo:
        raise RecursoInativoError("cadastro de cliente inativo; procure a barbearia")
    return existente


def criar_publico(
    session: Session,
    dados: AgendamentoPublicoIn,
    agora: datetime,
    slot_minutos: int | None = None,
) -> tuple[Agendamento, DadosConfirmacao]:
    try:
        disponibilidade_service.validar_janela_de_datas(
            dados.inicio.date(), agora, aceitar_passado=True
        )
        barbeiro = cadastro_service.obter_ativo(session, Barbeiro, dados.barbeiro_id, "barbeiro")
        servico = cadastro_service.obter_ativo(session, Servico, dados.servico_id, "serviço")
        cliente = _obter_ou_criar_cliente(session, dados)
        codigo = secrets.token_urlsafe(TAMANHO_CODIGO_BYTES)
        return _validar_e_gravar(
            session, cliente, barbeiro, servico, dados.inicio, agora, codigo, slot_minutos
        )
    except DominioError:
        session.rollback()
        raise


def cancelar(session: Session, agendamento_id: int) -> Agendamento:
    agendamento = obter(session, agendamento_id)
    if agendamento.status == StatusAgendamento.AGENDADO:
        agendamento.status = StatusAgendamento.CANCELADO
        session.commit()
    return agendamento


def _codigo_confere(informado: str, esperado: str | None) -> bool:
    if esperado is None:
        return False
    return secrets.compare_digest(informado.encode(), esperado.encode())


def cancelar_com_codigo(
    session: Session, agendamento_id: int, codigo: str, agora: datetime
) -> Agendamento:
    agendamento = agendamentos.obter(session, agendamento_id)
    if agendamento is None or not _codigo_confere(codigo, agendamento.codigo_cancelamento):
        raise RecursoNaoEncontradoError("agendamento não encontrado")
    if agendamento.status == StatusAgendamento.CANCELADO:
        return agendamento
    if agendamento.inicio <= agora:
        raise HorarioPassadoError("não é possível cancelar um horário que já passou")
    agendamento.status = StatusAgendamento.CANCELADO
    session.commit()
    return agendamento


def obter(session: Session, agendamento_id: int) -> Agendamento:
    agendamento = agendamentos.obter(session, agendamento_id)
    if agendamento is None:
        raise RecursoNaoEncontradoError(f"agendamento {agendamento_id} não encontrado")
    return agendamento


def listar(
    session: Session,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    dia: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
    limite: int | None = None,
    deslocamento: int = 0,
) -> list[Agendamento]:
    return agendamentos.listar(
        session, barbeiro_id, cliente_id, dia, status, desde, limite, deslocamento
    )


def pagina(
    session: Session,
    limite: int,
    deslocamento: int,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    dia: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
) -> tuple[list[Agendamento], int]:
    itens = agendamentos.listar(
        session, barbeiro_id, cliente_id, dia, status, desde, limite, deslocamento
    )
    total = agendamentos.contar(session, barbeiro_id, cliente_id, dia, status, desde)
    return itens, total
