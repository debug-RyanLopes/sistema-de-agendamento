from datetime import time
from decimal import Decimal

from app.database import SessionLocal, aplicar_migracoes, engine
from app.models import Barbeiro, Base, Cliente, Disponibilidade, Produto, Servico
from sqlalchemy import select

DIAS_UTEIS_E_SABADO = range(0, 6)


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
                Servico(nome="Corte de cabelo", duracao_minutos=30, preco=Decimal("45.0")),
                Servico(nome="Barba", duracao_minutos=20, preco=Decimal("30.0")),
                Servico(nome="Corte + barba", duracao_minutos=60, preco=Decimal("70.0")),
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
        session.commit()
        print("Dados de exemplo criados: 1 cliente, 2 barbeiros, 3 serviços, 2 produtos.")


if __name__ == "__main__":
    popular()
