from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models import Barbeiro, Disponibilidade, Servico
from app.repositories import agendamentos, disponibilidades
from app.schemas import DisponibilidadeIn
from app.services import cadastro_service


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


def _alinhar(momento: datetime, slot_minutos: int) -> datetime:
    minutos = momento.hour * 60 + momento.minute
    if momento.second or momento.microsecond:
        minutos += 1
    arredondado = -(-minutos // slot_minutos) * slot_minutos
    return datetime.combine(momento.date(), time.min) + timedelta(minutes=arredondado)


def _sobrepoe(inicio: datetime, fim: datetime, ocupados: list[tuple[datetime, datetime]]) -> bool:
    return any(inicio < o_fim and fim > o_inicio for o_inicio, o_fim in ocupados)


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
