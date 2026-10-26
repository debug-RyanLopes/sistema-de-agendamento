import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import CONFIG
from app.database import iniciar_escrita
from app.errors import (
    AcessoNegadoError,
    ConflitoHorarioError,
    DominioError,
    ForaDaDisponibilidadeError,
    HorarioInvalidoError,
    HorarioPassadoError,
    LimiteExcedidoError,
    RecursoInativoError,
    RecursoNaoEncontradoError,
    TransicaoInvalidaError,
)
from app.models import (
    CENTAVOS,
    STATUS_FINAIS_DO_PASSADO,
    Agendamento,
    Barbeiro,
    Cliente,
    Origem,
    Servico,
    StatusAgendamento,
)
from app.repositories import agendamentos, cadastros
from app.schemas import AgendamentoIn, AgendamentoPublicoIn
from app.services import cadastro_service, disponibilidade_service
from app.services.notificacao_service import DadosAgendamento

TAMANHO_CODIGO_BYTES = 8


def _validar_horario(
    session: Session,
    barbeiro: Barbeiro,
    inicio: datetime,
    fim: datetime,
    agora: datetime,
    slot_minutos: int | None,
    ignorar_id: int | None = None,
) -> None:
    if inicio <= agora:
        raise HorarioPassadoError("o horário escolhido já passou")
    if not disponibilidade_service.horario_alinhado(inicio, slot_minutos):
        raise HorarioInvalidoError(
            "o horário deve começar em múltiplos de "
            f"{slot_minutos or CONFIG.slot_minutes} minutos (ex.: 10:00, 10:30)"
        )
    if not disponibilidade_service.cobre(session, barbeiro.id, inicio, fim):
        raise ForaDaDisponibilidadeError("o horário está fora da disponibilidade do barbeiro")
    intervalo = disponibilidade_service.intervalo_entre_atendimentos()
    if agendamentos.existe_sobreposicao(
        session, barbeiro.id, inicio - intervalo, fim + intervalo, ignorar_id
    ):
        raise ConflitoHorarioError("o barbeiro já tem um agendamento nesse horário")


SEPARADOR_DE_SERVICOS = " + "


@dataclass(frozen=True, slots=True)
class ResumoServicos:
    """O que foi contratado num agendamento: nomes, ids, duração e preço somados."""

    ids: list[int]
    nomes: list[str]
    duracao_minutos: int
    preco: Decimal

    @property
    def descricao(self) -> str:
        return SEPARADOR_DE_SERVICOS.join(self.nomes)


def _resumir(servicos: list[Servico]) -> ResumoServicos:
    return ResumoServicos(
        ids=[servico.id for servico in servicos],
        nomes=[servico.nome for servico in servicos],
        duracao_minutos=sum(servico.duracao_minutos for servico in servicos),
        # Objetos recém-criados podem trazer float até o primeiro commit; normaliza.
        preco=sum((Decimal(str(s.preco)) for s in servicos), Decimal("0")).quantize(CENTAVOS),
    )


def resumo_dos_servicos(session: Session, agendamento: Agendamento) -> ResumoServicos:
    """Serviços do agendamento com o preço da época; agendamentos antigos usam o serviço único."""
    itens = agendamentos.servicos_dos_agendamentos(session, [agendamento.id]).get(agendamento.id)
    if itens:
        return ResumoServicos(
            ids=[item[0] for item in itens],
            nomes=[item[1] for item in itens],
            duracao_minutos=sum(item[3] for item in itens),
            preco=sum((item[2] for item in itens), Decimal("0")).quantize(CENTAVOS),
        )
    servico = cadastro_service.obter(session, Servico, agendamento.servico_id, "serviço")
    return ResumoServicos(
        ids=[servico.id],
        nomes=[servico.nome],
        duracao_minutos=int((agendamento.fim - agendamento.inicio).total_seconds() // 60),
        preco=agendamento.preco if agendamento.preco is not None else servico.preco,
    )


def _dados(
    agendamento: Agendamento, cliente: Cliente, barbeiro: Barbeiro, resumo: ResumoServicos
) -> DadosAgendamento:
    return DadosAgendamento(
        email=cliente.email,
        cliente=cliente.nome,
        barbeiro=barbeiro.nome,
        servico=resumo.descricao,
        inicio=agendamento.inicio,
        preco=resumo.preco,
        agendamento_id=agendamento.id,
        codigo_cancelamento=agendamento.codigo_cancelamento,
    )


def _validar_e_gravar(
    session: Session,
    cliente: Cliente,
    barbeiro: Barbeiro,
    servicos: list[Servico],
    inicio: datetime,
    agora: datetime,
    codigo_cancelamento: str | None,
    slot_minutos: int | None,
    origem: Origem,
) -> tuple[Agendamento, DadosAgendamento]:
    resumo = _resumir(servicos)
    fim = inicio + timedelta(minutes=resumo.duracao_minutos)
    agendamentos.travar_agenda_do_barbeiro(session, barbeiro.id)
    _validar_horario(session, barbeiro, inicio, fim, agora, slot_minutos)
    agendamento = agendamentos.adicionar(
        session,
        Agendamento(
            cliente_id=cliente.id,
            barbeiro_id=barbeiro.id,
            servico_id=servicos[0].id,
            inicio=inicio,
            fim=fim,
            status=StatusAgendamento.AGENDADO,
            codigo_cancelamento=codigo_cancelamento,
            criado_em=agora,
            origem=origem,
            preco=resumo.preco,
        ),
    )
    agendamentos.adicionar_servicos(session, agendamento, servicos)
    session.commit()
    return agendamento, _dados(agendamento, cliente, barbeiro, resumo)


def criar(
    session: Session, dados: AgendamentoIn, agora: datetime, slot_minutos: int | None = None
) -> tuple[Agendamento, DadosAgendamento]:
    iniciar_escrita(session)
    cliente = cadastro_service.obter_ativo(session, Cliente, dados.cliente_id, "cliente")
    barbeiro = cadastro_service.obter_ativo(session, Barbeiro, dados.barbeiro_id, "barbeiro")
    servicos = disponibilidade_service.servicos_escolhidos(session, dados.servicos)
    return _validar_e_gravar(
        session,
        cliente,
        barbeiro,
        servicos,
        dados.inicio,
        agora,
        None,
        slot_minutos,
        Origem.EMPRESA,
    )


def _obter_ou_criar_cliente(session: Session, dados: AgendamentoPublicoIn) -> Cliente:
    existente = cadastros.obter_cliente_por_email(session, dados.email)
    if existente is None:
        return cadastros.adicionar(
            session, Cliente(nome=dados.nome, email=dados.email, telefone=dados.telefone)
        )
    if not existente.ativo:
        # Mensagem genérica de propósito: não confirma que o e-mail está cadastrado.
        raise RecursoInativoError(
            "não foi possível concluir o agendamento com estes dados; procure a barbearia"
        )
    return existente


def _verificar_limites(session: Session, cliente: Cliente, telefone: str, agora: datetime) -> None:
    maximo = CONFIG.max_agendamentos_ativos_por_cliente
    if maximo <= 0:
        return
    por_email = agendamentos.contar_ativos_do_cliente(session, cliente.id, agora)
    por_telefone = agendamentos.contar_ativos_por_telefone(session, telefone, agora)
    if max(por_email, por_telefone) >= maximo:
        raise LimiteExcedidoError(
            f"você já tem {maximo} horários marcados; cancele um deles para marcar outro"
        )


def criar_publico(
    session: Session,
    dados: AgendamentoPublicoIn,
    agora: datetime,
    slot_minutos: int | None = None,
) -> tuple[Agendamento, DadosAgendamento]:
    iniciar_escrita(session)
    try:
        disponibilidade_service.validar_janela_de_datas(
            dados.inicio.date(), agora, aceitar_passado=True
        )
        servicos = disponibilidade_service.servicos_escolhidos(session, dados.servicos)
        if dados.barbeiro_id is None:
            barbeiro = disponibilidade_service.escolher_barbeiro(
                session,
                disponibilidade_service.duracao_total(servicos),
                dados.inicio,
                agora,
                slot_minutos or CONFIG.slot_minutes,
            )
        else:
            barbeiro = cadastro_service.obter_ativo(
                session, Barbeiro, dados.barbeiro_id, "barbeiro"
            )
        cliente = _obter_ou_criar_cliente(session, dados)
        _verificar_limites(session, cliente, dados.telefone, agora)
        codigo = secrets.token_urlsafe(TAMANHO_CODIGO_BYTES)
        return _validar_e_gravar(
            session,
            cliente,
            barbeiro,
            servicos,
            dados.inicio,
            agora,
            codigo,
            slot_minutos,
            Origem.CLIENTE,
        )
    except DominioError:
        session.rollback()
        raise


def dados_para_notificacao(session: Session, agendamento: Agendamento) -> DadosAgendamento:
    cliente = cadastro_service.obter(session, Cliente, agendamento.cliente_id, "cliente")
    barbeiro = cadastro_service.obter(session, Barbeiro, agendamento.barbeiro_id, "barbeiro")
    return _dados(agendamento, cliente, barbeiro, resumo_dos_servicos(session, agendamento))


def _cancelar(agendamento: Agendamento, agora: datetime, por: Origem, motivo: str | None) -> bool:
    """Marca como cancelado. Devolve False se já estava cancelado (idempotente)."""
    if agendamento.status == StatusAgendamento.CANCELADO:
        return False
    if agendamento.status in STATUS_FINAIS_DO_PASSADO:
        raise TransicaoInvalidaError(f"agendamento já encerrado como '{agendamento.status.value}'")
    if agendamento.inicio <= agora:
        raise HorarioPassadoError(
            "não é possível cancelar um horário que já passou; marque como concluído ou falta"
        )
    agendamento.status = StatusAgendamento.CANCELADO
    agendamento.cancelado_em = agora
    agendamento.cancelado_por = por
    agendamento.motivo_cancelamento = motivo
    return True


def _verificar_dono_da_agenda(agendamento: Agendamento, somente_do_barbeiro: int | None) -> None:
    if somente_do_barbeiro is not None and agendamento.barbeiro_id != somente_do_barbeiro:
        raise AcessoNegadoError("este agendamento é de outro barbeiro")


def obter_para(
    session: Session, agendamento_id: int, somente_do_barbeiro: int | None
) -> Agendamento:
    agendamento = obter(session, agendamento_id)
    _verificar_dono_da_agenda(agendamento, somente_do_barbeiro)
    return agendamento


def cancelar(
    session: Session,
    agendamento_id: int,
    agora: datetime,
    *,
    por: Origem = Origem.EMPRESA,
    motivo: str | None = None,
    somente_do_barbeiro: int | None = None,
) -> tuple[Agendamento, bool]:
    """Cancela e devolve (agendamento, cancelou_agora). Já cancelado devolve False."""
    iniciar_escrita(session)
    agendamento = obter_para(session, agendamento_id, somente_do_barbeiro)
    cancelou = _cancelar(agendamento, agora, por, motivo)
    if cancelou:
        session.commit()
    return agendamento, cancelou


def _codigo_confere(informado: str, esperado: str | None) -> bool:
    if esperado is None:
        return False
    return secrets.compare_digest(informado.encode(), esperado.encode())


def _obter_com_codigo(session: Session, agendamento_id: int, codigo: str) -> Agendamento:
    agendamento = agendamentos.obter(session, agendamento_id)
    if agendamento is None or not _codigo_confere(codigo, agendamento.codigo_cancelamento):
        raise RecursoNaoEncontradoError("agendamento não encontrado")
    return agendamento


def cancelar_com_codigo(
    session: Session, agendamento_id: int, codigo: str, agora: datetime
) -> tuple[Agendamento, bool]:
    iniciar_escrita(session)
    agendamento = _obter_com_codigo(session, agendamento_id, codigo)
    cancelou = _cancelar(agendamento, agora, Origem.CLIENTE, None)
    if cancelou:
        session.commit()
    return agendamento, cancelou


def marcar_status(
    session: Session,
    agendamento_id: int,
    status: StatusAgendamento,
    agora: datetime,
    somente_do_barbeiro: int | None = None,
) -> Agendamento:
    """Encerra um atendimento que já aconteceu: concluído ou cliente não compareceu."""
    iniciar_escrita(session)
    if status not in STATUS_FINAIS_DO_PASSADO:
        raise TransicaoInvalidaError("use 'concluido' ou 'nao_compareceu'")
    agendamento = obter_para(session, agendamento_id, somente_do_barbeiro)
    if agendamento.status == status:
        return agendamento
    if agendamento.status != StatusAgendamento.AGENDADO:
        raise TransicaoInvalidaError(
            f"agendamento está '{agendamento.status.value}' e não pode mudar para '{status.value}'"
        )
    if agendamento.inicio > agora:
        raise TransicaoInvalidaError("o atendimento ainda não aconteceu")
    agendamento.status = status
    session.commit()
    return agendamento


def _reagendar(
    session: Session,
    agendamento: Agendamento,
    novo_inicio: datetime,
    agora: datetime,
    slot_minutos: int | None,
) -> tuple[Agendamento, DadosAgendamento]:
    if agendamento.status != StatusAgendamento.AGENDADO:
        raise TransicaoInvalidaError("só agendamentos ativos podem ser remarcados")
    if agendamento.inicio <= agora:
        raise HorarioPassadoError("não é possível remarcar um horário que já passou")
    barbeiro = cadastro_service.obter_ativo(session, Barbeiro, agendamento.barbeiro_id, "barbeiro")
    cliente = cadastro_service.obter(session, Cliente, agendamento.cliente_id, "cliente")
    resumo = resumo_dos_servicos(session, agendamento)
    fim = novo_inicio + timedelta(minutes=resumo.duracao_minutos)
    agendamentos.travar_agenda_do_barbeiro(session, barbeiro.id)
    _validar_horario(session, barbeiro, novo_inicio, fim, agora, slot_minutos, agendamento.id)
    agendamento.inicio = novo_inicio
    agendamento.fim = fim
    agendamento.lembrete_enviado_em = None
    session.commit()
    return agendamento, _dados(agendamento, cliente, barbeiro, resumo)


def reagendar(
    session: Session,
    agendamento_id: int,
    novo_inicio: datetime,
    agora: datetime,
    slot_minutos: int | None = None,
    somente_do_barbeiro: int | None = None,
) -> tuple[Agendamento, DadosAgendamento]:
    iniciar_escrita(session)
    agendamento = obter_para(session, agendamento_id, somente_do_barbeiro)
    return _reagendar(session, agendamento, novo_inicio, agora, slot_minutos)


def reagendar_com_codigo(
    session: Session,
    agendamento_id: int,
    codigo: str,
    novo_inicio: datetime,
    agora: datetime,
    slot_minutos: int | None = None,
) -> tuple[Agendamento, DadosAgendamento]:
    iniciar_escrita(session)
    try:
        disponibilidade_service.validar_janela_de_datas(novo_inicio.date(), agora)
        agendamento = _obter_com_codigo(session, agendamento_id, codigo)
        return _reagendar(session, agendamento, novo_inicio, agora, slot_minutos)
    except DominioError:
        session.rollback()
        raise


def meus_agendamentos(
    session: Session, email: str, agora: datetime
) -> list[tuple[Agendamento, str, str]]:
    """Agendamentos futuros do cliente com este e-mail: (agendamento, barbeiro, serviço)."""
    cliente = cadastros.obter_cliente_por_email(session, email)
    if cliente is None:
        return []
    futuros = agendamentos.listar_futuros_do_cliente(session, cliente.id, agora)
    combos = agendamentos.servicos_dos_agendamentos(session, [a.id for a, *_ in futuros])
    return [
        (agendamento, barbeiro, descrever_servicos(combos.get(agendamento.id), servico))
        for agendamento, barbeiro, servico, _preco in futuros
    ]


def servicos_de_varios(
    session: Session, itens: list[Agendamento]
) -> dict[int, tuple[list[int], Decimal]]:
    """Por agendamento: (ids dos serviços, preço), em uma consulta só; antigos usam a reserva."""
    combos = agendamentos.servicos_dos_agendamentos(session, [item.id for item in itens])
    precos_reserva = {
        servico.id: servico.preco
        for servico in cadastros.listar(session, Servico, incluir_inativos=True)
    }
    resultado = {}
    for item in itens:
        linhas = combos.get(item.id)
        if linhas:
            preco = sum((linha[2] for linha in linhas), Decimal("0"))
            resultado[item.id] = ([linha[0] for linha in linhas], preco.quantize(CENTAVOS))
        else:
            preco = item.preco if item.preco is not None else precos_reserva.get(item.servico_id)
            resultado[item.id] = ([item.servico_id], preco)
    return resultado


def descrever_servicos(itens: list[tuple[int, str, Decimal, int]] | None, reserva: str) -> str:
    """'Corte de cabelo + Barba' a partir das linhas do combo, ou o nome do serviço único."""
    return SEPARADOR_DE_SERVICOS.join(item[1] for item in itens) if itens else reserva


def ids_dos_servicos(itens: list[tuple[int, str, Decimal, int]] | None, reserva: int) -> list[int]:
    return [item[0] for item in itens] if itens else [reserva]


def obter(session: Session, agendamento_id: int) -> Agendamento:
    agendamento = agendamentos.obter(session, agendamento_id)
    if agendamento is None:
        raise RecursoNaoEncontradoError(f"agendamento {agendamento_id} não encontrado")
    return agendamento


def obter_com_codigo(session: Session, agendamento_id: int, codigo: str) -> Agendamento:
    return _obter_com_codigo(session, agendamento_id, codigo)


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
    ate: date | None = None,
) -> tuple[list[Agendamento], int]:
    itens = agendamentos.listar(
        session, barbeiro_id, cliente_id, dia, status, desde, limite, deslocamento, ate
    )
    total = agendamentos.contar(session, barbeiro_id, cliente_id, dia, status, desde, ate)
    return itens, total
