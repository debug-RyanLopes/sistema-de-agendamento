from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.config import CONFIG
from app.errors import DataForaDaJanelaError, RecursoNaoEncontradoError
from app.models import Barbeiro, Disponibilidade, Servico
from app.repositories import agendamentos, cadastros, disponibilidades
from app.schemas import DisponibilidadeIn
from app.services import cadastro_service
from app.tempo import ultimo_dia_do_mes


def cadastrar_janela(
    session: Session, barbeiro_id: int, dados: DisponibilidadeIn
) -> Disponibilidade:
    cadastro_service.obter(session, Barbeiro, barbeiro_id, "barbeiro")
    janela = disponibilidades.adicionar(
        session, Disponibilidade(barbeiro_id=barbeiro_id, **dados.model_dump())
    )
    session.commit()
    return janela


def listar_janelas(session: Session, barbeiro_id: int) -> list[Disponibilidade]:
    cadastro_service.obter(session, Barbeiro, barbeiro_id, "barbeiro")
    return disponibilidades.listar_por_barbeiro(session, barbeiro_id)


def remover_janela(session: Session, barbeiro_id: int, janela_id: int) -> None:
    cadastro_service.obter(session, Barbeiro, barbeiro_id, "barbeiro")
    janela = disponibilidades.obter(session, janela_id)
    if janela is None or janela.barbeiro_id != barbeiro_id:
        raise RecursoNaoEncontradoError(f"janela {janela_id} não encontrada")
    disponibilidades.remover(session, janela)
    session.commit()


def _alinhar(momento: datetime, slot_minutos: int) -> datetime:
    minutos = momento.hour * 60 + momento.minute
    if momento.second or momento.microsecond:
        minutos += 1
    arredondado = -(-minutos // slot_minutos) * slot_minutos
    return datetime.combine(momento.date(), time.min) + timedelta(minutes=arredondado)


def horario_alinhado(momento: datetime, slot_minutos: int | None = None) -> bool:
    slot = slot_minutos or CONFIG.slot_minutes
    minutos = momento.hour * 60 + momento.minute
    return momento.second == 0 and momento.microsecond == 0 and minutos % slot == 0


def validar_janela_de_datas(dia: date, agora: datetime, *, aceitar_passado: bool = False) -> None:
    """A área do cliente só enxerga de hoje até o último dia do mês corrente."""
    limite = ultimo_dia_do_mes(agora.date())
    if dia > limite or (dia < agora.date() and not aceitar_passado):
        raise DataForaDaJanelaError(
            f"escolha uma data entre {agora.date():%d/%m/%Y} e {limite:%d/%m/%Y}"
        )


def _sobrepoe(inicio: datetime, fim: datetime, ocupados: list[tuple[datetime, datetime]]) -> bool:
    return any(inicio < o_fim and fim > o_inicio for o_inicio, o_fim in ocupados)


def _calcular_horarios(
    session: Session,
    barbeiro_id: int,
    servico: Servico,
    dia: date,
    agora: datetime,
    slot_minutos: int,
) -> list[datetime]:
    duracao = timedelta(minutes=servico.duracao_minutos)
    passo = timedelta(minutes=slot_minutos)
    ocupados = [
        (item.inicio, item.fim)
        for item in agendamentos.listar_ativos_no_dia(session, barbeiro_id, dia)
    ]
    livres: set[datetime] = set()
    for janela in disponibilidades.listar_por_dia(session, barbeiro_id, dia.weekday()):
        limite = datetime.combine(dia, janela.hora_fim)
        cursor = _alinhar(datetime.combine(dia, janela.hora_inicio), slot_minutos)
        while cursor + duracao <= limite:
            if cursor > agora and not _sobrepoe(cursor, cursor + duracao, ocupados):
                livres.add(cursor)
            cursor += passo
    return sorted(livres)


def horarios_livres(
    session: Session,
    barbeiro_id: int,
    servico_id: int,
    dia: date,
    agora: datetime,
    slot_minutos: int,
) -> list[datetime]:
    cadastro_service.obter(session, Barbeiro, barbeiro_id, "barbeiro")
    servico = cadastro_service.obter(session, Servico, servico_id, "serviço")
    return _calcular_horarios(session, barbeiro_id, servico, dia, agora, slot_minutos)


def barbeiros_disponiveis(
    session: Session, servico_id: int, dia: date, agora: datetime, slot_minutos: int
) -> list[tuple[Barbeiro, list[datetime]]]:
    servico = cadastro_service.obter_ativo(session, Servico, servico_id, "serviço")
    validar_janela_de_datas(dia, agora)
    resultado = []
    for barbeiro in cadastros.listar(session, Barbeiro, incluir_inativos=False):
        horarios = _calcular_horarios(session, barbeiro.id, servico, dia, agora, slot_minutos)
        if horarios:
            resultado.append((barbeiro, horarios))
    return resultado
