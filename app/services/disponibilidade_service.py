from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.config import CONFIG
from app.database import iniciar_escrita
from app.errors import DataForaDaJanelaError, HorarioInvalidoError, RecursoNaoEncontradoError
from app.models import Barbeiro, Bloqueio, Disponibilidade, Servico
from app.repositories import agendamentos, bloqueios, cadastros, disponibilidades
from app.schemas import BloqueioIn, DisponibilidadeIn
from app.services import cadastro_service
from app.tempo import ultimo_dia_do_mes

Intervalo = tuple[datetime, datetime]


def cadastrar_janela(
    session: Session, barbeiro_id: int, dados: DisponibilidadeIn
) -> Disponibilidade:
    iniciar_escrita(session)
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
    iniciar_escrita(session)
    cadastro_service.obter(session, Barbeiro, barbeiro_id, "barbeiro")
    janela = disponibilidades.obter(session, janela_id)
    if janela is None or janela.barbeiro_id != barbeiro_id:
        raise RecursoNaoEncontradoError(f"janela {janela_id} não encontrada")
    disponibilidades.remover(session, janela)
    session.commit()


# --- bloqueios: folgas, feriados e bloqueios pontuais ---------------------------------


def criar_bloqueio(session: Session, dados: BloqueioIn) -> Bloqueio:
    iniciar_escrita(session)
    if dados.barbeiro_id is not None:
        cadastro_service.obter(session, Barbeiro, dados.barbeiro_id, "barbeiro")
    bloqueio = bloqueios.adicionar(session, Bloqueio(**dados.model_dump()))
    session.commit()
    return bloqueio


def listar_bloqueios(
    session: Session, desde: date | None = None, barbeiro_id: int | None = None
) -> list[Bloqueio]:
    return bloqueios.listar(session, desde, barbeiro_id)


def remover_bloqueio(session: Session, bloqueio_id: int) -> None:
    iniciar_escrita(session)
    bloqueio = bloqueios.obter(session, bloqueio_id)
    if bloqueio is None:
        raise RecursoNaoEncontradoError(f"bloqueio {bloqueio_id} não encontrado")
    bloqueios.remover(session, bloqueio)
    session.commit()


# --- cálculo de horários ---------------------------------------------------------------


def _fundir(intervalos: list[Intervalo]) -> list[Intervalo]:
    """Junta intervalos que se sobrepõem ou se encostam (9-12 e 12-18 viram 9-18)."""
    fundidos: list[Intervalo] = []
    for inicio, fim in sorted(intervalos):
        if fundidos and inicio <= fundidos[-1][1]:
            fundidos[-1] = (fundidos[-1][0], max(fundidos[-1][1], fim))
        else:
            fundidos.append((inicio, fim))
    return fundidos


def _subtrair(intervalos: list[Intervalo], bloqueados: list[Intervalo]) -> list[Intervalo]:
    for b_inicio, b_fim in bloqueados:
        restantes: list[Intervalo] = []
        for inicio, fim in intervalos:
            if b_fim <= inicio or b_inicio >= fim:
                restantes.append((inicio, fim))
                continue
            if inicio < b_inicio:
                restantes.append((inicio, b_inicio))
            if b_fim < fim:
                restantes.append((b_fim, fim))
        intervalos = restantes
    return intervalos


def _intervalo_do_bloqueio(bloqueio: Bloqueio, dia: date) -> Intervalo:
    if bloqueio.hora_inicio is None or bloqueio.hora_fim is None:
        return datetime.combine(dia, time.min), datetime.combine(dia, time.min) + timedelta(days=1)
    return datetime.combine(dia, bloqueio.hora_inicio), datetime.combine(dia, bloqueio.hora_fim)


def janelas_do_dia(session: Session, barbeiro_id: int, dia: date) -> list[Intervalo]:
    """Janelas de trabalho do barbeiro no dia, fundidas e já descontados os bloqueios."""
    janelas = _fundir(
        [
            (datetime.combine(dia, janela.hora_inicio), datetime.combine(dia, janela.hora_fim))
            for janela in disponibilidades.listar_por_dia(session, barbeiro_id, dia.weekday())
        ]
    )
    bloqueados = [
        _intervalo_do_bloqueio(bloqueio, dia)
        for bloqueio in bloqueios.listar_do_dia(session, barbeiro_id, dia)
    ]
    return _subtrair(janelas, bloqueados)


def cobre(session: Session, barbeiro_id: int, inicio: datetime, fim: datetime) -> bool:
    return any(
        j_inicio <= inicio and fim <= j_fim
        for j_inicio, j_fim in janelas_do_dia(session, barbeiro_id, inicio.date())
    )


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


def intervalo_entre_atendimentos(minutos: int | None = None) -> timedelta:
    return timedelta(minutes=CONFIG.intervalo_minutos if minutos is None else minutos)


def _sobrepoe(
    inicio: datetime, fim: datetime, ocupados: list[Intervalo], intervalo: timedelta
) -> bool:
    return any(
        inicio < o_fim + intervalo and fim + intervalo > o_inicio for o_inicio, o_fim in ocupados
    )


def _passo_da_grade(duracao_minutos: int, slot_minutos: int) -> timedelta:
    """Os horários oferecidos avançam pela duração do serviço (arredondada ao slot).

    Um corte de 30 min aparece como 09:00, 09:30, 10:00...; um combo de 60 min como
    09:00, 10:00, 11:00... Assim a agenda não fica picada em sobras inúteis.
    """
    multiplo = max(1, -(-duracao_minutos // slot_minutos))
    return timedelta(minutes=multiplo * slot_minutos)


def _calcular_horarios(
    session: Session,
    barbeiro_id: int,
    duracao_minutos: int,
    dia: date,
    agora: datetime,
    slot_minutos: int,
    ignorar_agendamento_id: int | None = None,
) -> list[datetime]:
    duracao = timedelta(minutes=duracao_minutos)
    passo = _passo_da_grade(duracao_minutos, slot_minutos)
    intervalo = intervalo_entre_atendimentos()
    ocupados = [
        (item.inicio, item.fim)
        for item in agendamentos.listar_ativos_no_dia(
            session, barbeiro_id, dia, ignorar_agendamento_id
        )
    ]
    candidatos: set[datetime] = set()
    for j_inicio, j_fim in janelas_do_dia(session, barbeiro_id, dia):
        cursor = _alinhar(j_inicio, slot_minutos)
        while cursor + duracao <= j_fim:
            candidatos.add(cursor)
            cursor += passo
        # Logo depois de cada atendimento já marcado também é uma boa opção: evita buracos.
        for _o_inicio, o_fim in ocupados:
            depois = _alinhar(o_fim + intervalo, slot_minutos)
            if j_inicio <= depois and depois + duracao <= j_fim:
                candidatos.add(depois)
    return sorted(
        c for c in candidatos if c > agora and not _sobrepoe(c, c + duracao, ocupados, intervalo)
    )


def _ids(servico_ids: int | list[int]) -> list[int]:
    return [servico_ids] if isinstance(servico_ids, int) else list(servico_ids)


def servicos_escolhidos(session: Session, servico_ids: int | list[int]) -> list[Servico]:
    """Serviços ativos, na ordem pedida; levanta 404/422 como o resto da aplicação."""
    return [
        cadastro_service.obter_ativo(session, Servico, item, "serviço")
        for item in _ids(servico_ids)
    ]


def duracao_total(servicos: list[Servico]) -> int:
    return sum(servico.duracao_minutos for servico in servicos)


def horarios_livres(
    session: Session,
    barbeiro_id: int,
    servico_ids: int | list[int],
    dia: date,
    agora: datetime,
    slot_minutos: int,
) -> list[datetime]:
    cadastro_service.obter(session, Barbeiro, barbeiro_id, "barbeiro")
    servicos = [cadastro_service.obter(session, Servico, i, "serviço") for i in _ids(servico_ids)]
    return _calcular_horarios(
        session, barbeiro_id, duracao_total(servicos), dia, agora, slot_minutos
    )


def barbeiros_disponiveis(
    session: Session,
    servico_ids: int | list[int],
    dia: date,
    agora: datetime,
    slot_minutos: int,
) -> list[tuple[Barbeiro, list[datetime]]]:
    duracao = duracao_total(servicos_escolhidos(session, servico_ids))
    validar_janela_de_datas(dia, agora)
    resultado = []
    for barbeiro in cadastros.listar(session, Barbeiro, incluir_inativos=False):
        horarios = _calcular_horarios(session, barbeiro.id, duracao, dia, agora, slot_minutos)
        if horarios:
            resultado.append((barbeiro, horarios))
    return resultado


def escolher_barbeiro(
    session: Session, duracao_minutos: int, inicio: datetime, agora: datetime, slot_minutos: int
) -> Barbeiro:
    """ "Qualquer barbeiro": o ativo que tem o horário livre e menos agendamentos no dia."""
    candidatos = []
    for barbeiro in cadastros.listar(session, Barbeiro, incluir_inativos=False):
        livres = _calcular_horarios(
            session, barbeiro.id, duracao_minutos, inicio.date(), agora, slot_minutos
        )
        if inicio in livres:
            ocupacao = len(agendamentos.listar_ativos_no_dia(session, barbeiro.id, inicio.date()))
            candidatos.append((ocupacao, barbeiro.id, barbeiro))
    if not candidatos:
        raise HorarioInvalidoError("nenhum barbeiro tem esse horário livre")
    return min(candidatos)[2]
