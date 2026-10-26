import csv
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.errors import HorarioInvalidoError
from app.models import CENTAVOS, Barbeiro, StatusAgendamento
from app.repositories import agendamentos, cadastros
from app.schemas import ResumoBarbeiroOut, ResumoOut
from app.services import disponibilidade_service, venda_service

MAXIMO_DIAS = 92


def _minutos_disponiveis(session: Session, barbeiro_id: int, desde: date, ate: date) -> int:
    total = 0
    dia = desde
    while dia <= ate:
        for inicio, fim in disponibilidade_service.janelas_do_dia(session, barbeiro_id, dia):
            total += int((fim - inicio).total_seconds() // 60)
        dia += timedelta(days=1)
    return total


def resumo(session: Session, desde: date, ate: date) -> ResumoOut:
    """Ocupação e receita por barbeiro no período (inclusive), limitado a 92 dias."""
    if ate < desde:
        raise HorarioInvalidoError("'ate' deve ser igual ou posterior a 'desde'")
    if (ate - desde).days >= MAXIMO_DIAS:
        raise HorarioInvalidoError(f"o período máximo é de {MAXIMO_DIAS} dias")
    inicio = datetime.combine(desde, time.min)
    fim = datetime.combine(ate, time.min) + timedelta(days=1)

    por_barbeiro: dict[int, dict] = {}
    for barbeiro in cadastros.listar(session, Barbeiro, incluir_inativos=True):
        por_barbeiro[barbeiro.id] = {
            "barbeiro_id": barbeiro.id,
            "nome": barbeiro.nome,
            "agendados": 0,
            "concluidos": 0,
            "cancelados": 0,
            "faltas": 0,
            "receita": Decimal("0"),
            "minutos_ocupados": 0,
        }
    campo = {
        StatusAgendamento.AGENDADO: "agendados",
        StatusAgendamento.CONCLUIDO: "concluidos",
        StatusAgendamento.CANCELADO: "cancelados",
        StatusAgendamento.NAO_COMPARECEU: "faltas",
    }
    for (
        barbeiro_id,
        _nome,
        status,
        quantidade,
        receita,
        minutos,
    ) in agendamentos.resumo_por_barbeiro(session, inicio, fim):
        linha = por_barbeiro[barbeiro_id]
        linha[campo[status]] += quantidade
        if status in (StatusAgendamento.AGENDADO, StatusAgendamento.CONCLUIDO):
            linha["receita"] += Decimal(str(receita))
            linha["minutos_ocupados"] += int(round(float(minutos)))

    barbeiros = []
    for linha in por_barbeiro.values():
        disponiveis = _minutos_disponiveis(session, linha["barbeiro_id"], desde, ate)
        barbeiros.append(
            ResumoBarbeiroOut(
                **{**linha, "receita": linha["receita"].quantize(CENTAVOS)},
                minutos_disponiveis=disponiveis,
                ocupacao=round(linha["minutos_ocupados"] / disponiveis, 3) if disponiveis else 0.0,
            )
        )
    return ResumoOut(
        desde=desde,
        ate=ate,
        total_agendamentos=sum(
            b.agendados + b.concluidos + b.cancelados + b.faltas for b in barbeiros
        ),
        receita=sum((b.receita for b in barbeiros), Decimal("0")).quantize(CENTAVOS),
        receita_produtos=venda_service.receita(session, inicio, fim),
        barbeiros=barbeiros,
    )


def agendamentos_csv(
    session: Session,
    barbeiro_id: int | None = None,
    cliente_id: int | None = None,
    dia: date | None = None,
    status: StatusAgendamento | None = None,
    desde: date | None = None,
    ate: date | None = None,
) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(
        ["id", "inicio", "fim", "cliente", "barbeiro", "servico", "preco", "status", "origem"]
    )
    for agendamento, cliente, barbeiro, servico, preco in agendamentos.listar_detalhado(
        session, barbeiro_id, cliente_id, dia, status, desde, ate
    ):
        escritor.writerow(
            [
                agendamento.id,
                agendamento.inicio.isoformat(sep=" ", timespec="minutes"),
                agendamento.fim.isoformat(sep=" ", timespec="minutes"),
                cliente,
                barbeiro,
                servico,
                f"{preco:.2f}".replace(".", ","),
                agendamento.status.value,
                agendamento.origem.value if agendamento.origem else "",
            ]
        )
    return saida.getvalue()
