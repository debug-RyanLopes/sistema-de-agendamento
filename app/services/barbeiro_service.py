from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import CENTAVOS, Barbeiro
from app.repositories import agendamentos
from app.schemas import AgendamentoFuturoOut, ImpactoDesativacaoOut
from app.services import cadastro_service


def impacto_desativacao(
    session: Session, barbeiro_id: int, agora: datetime
) -> ImpactoDesativacaoOut:
    """O que a empresa precisa saber antes de tirar um barbeiro de circulação."""
    barbeiro = cadastro_service.obter(session, Barbeiro, barbeiro_id, "barbeiro")
    futuros = [
        AgendamentoFuturoOut(
            id=agendamento.id,
            inicio=agendamento.inicio,
            cliente=cliente,
            servico=servico,
            preco=preco,
        )
        for agendamento, cliente, servico, preco in agendamentos.listar_futuros_do_barbeiro(
            session, barbeiro_id, agora
        )
    ]
    return ImpactoDesativacaoOut(
        barbeiro_id=barbeiro.id,
        nome=barbeiro.nome,
        ativo=barbeiro.ativo,
        cadastrado_em=barbeiro.criado_em,
        dias_na_empresa=(
            max((agora - barbeiro.criado_em).days, 0) if barbeiro.criado_em else None
        ),
        atendimentos_realizados=agendamentos.contar_realizados(session, barbeiro_id, agora),
        faltas=agendamentos.contar_faltas(session, barbeiro_id),
        total_futuros=len(futuros),
        valor_futuro=sum((item.preco for item in futuros), Decimal("0")).quantize(CENTAVOS),
        proximo_atendimento=futuros[0].inicio if futuros else None,
        agendamentos_futuros=futuros,
    )
