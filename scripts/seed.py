from datetime import time, timedelta
from decimal import Decimal

from app.database import SessionLocal, aplicar_migracoes, engine
from app.models import Barbeiro, Base, Bloqueio, Cliente, Disponibilidade, Produto, Servico
from app.tempo import agora_local
from sqlalchemy import select

DIAS_UTEIS_E_SABADO = range(0, 6)

# O cliente monta o próprio combo marcando mais de um serviço (ex.: Corte + Barba).
SERVICOS = [
    Servico(nome="Corte de cabelo", duracao_minutos=30, preco=Decimal("45.0")),
    Servico(nome="Barba", duracao_minutos=20, preco=Decimal("30.0")),
    Servico(nome="Bigode", duracao_minutos=15, preco=Decimal("15.0")),
    Servico(nome="Acabamento/Pezinho", duracao_minutos=15, preco=Decimal("15.0")),
    Servico(nome="Sobrancelhas", duracao_minutos=15, preco=Decimal("15.0")),
    Servico(nome="Hidratação", duracao_minutos=30, preco=Decimal("40.0")),
    Servico(nome="Luzes", duracao_minutos=90, preco=Decimal("120.0")),
]


def popular() -> None:
    Base.metadata.create_all(engine)
    aplicar_migracoes(engine)
    with SessionLocal() as session:
        if session.scalars(select(Barbeiro)).first() is not None:
            print("Banco já possui dados; nada a fazer.")
            return
        barbeiros = [
            Barbeiro(nome="João Barbeiro", email="joao@barbearia.com"),
            Barbeiro(nome="Pedro Navalha", email="pedro@barbearia.com"),
        ]
        session.add_all(
            [
                Cliente(nome="Carlos Silva", email="carlos@exemplo.com", telefone="11987654321"),
                *SERVICOS,
                Produto(nome="Pomada modeladora", preco=Decimal("35.9"), estoque=12),
                Produto(nome="Óleo para barba", preco=Decimal("42.0"), estoque=8),
                *barbeiros,
            ]
        )
        session.flush()
        session.add_all(
            Disponibilidade(
                barbeiro_id=barbeiro.id,
                dia_semana=dia,
                hora_inicio=time(9, 0),
                hora_fim=time(18, 0),
            )
            for barbeiro in barbeiros
            for dia in DIAS_UTEIS_E_SABADO
        )
        # Exemplos de bloqueio: almoço do João amanhã e a barbearia fechada daqui a 7 dias.
        hoje = agora_local().date()
        session.add_all(
            [
                Bloqueio(
                    barbeiro_id=barbeiros[0].id,
                    data=hoje + timedelta(days=1),
                    hora_inicio=time(12, 0),
                    hora_fim=time(13, 0),
                    motivo="Almoço",
                ),
                Bloqueio(data=hoje + timedelta(days=7), motivo="Feriado (exemplo)"),
            ]
        )
        session.commit()
        print(
            "Dados de exemplo criados: 1 cliente, 2 barbeiros, 7 serviços, 2 produtos, "
            "2 bloqueios. O usuário 'admin' é criado na primeira subida da área da empresa."
        )


if __name__ == "__main__":
    popular()
