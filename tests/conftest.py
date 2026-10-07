from collections.abc import Iterator
from dataclasses import dataclass
from datetime import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies import get_agora, get_db, get_notificador
from app.main import app
from app.models import Barbeiro, Base, Cliente, Disponibilidade, Servico
from tests.helpers import AGORA_FIXO, NotificadorFalso


@dataclass
class Cenario:
    cliente: Cliente
    barbeiro: Barbeiro
    servico_30: Servico
    servico_60: Servico


@pytest.fixture
def engine() -> Iterator[Engine]:
    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as sessao:
        yield sessao


@pytest.fixture
def cenario(session: Session) -> Cenario:
    cliente = Cliente(nome="Carlos Silva", email="carlos@exemplo.com", telefone="11987654321")
    barbeiro = Barbeiro(nome="João Barbeiro", email="joao@barbearia.com")
    servico_30 = Servico(nome="Corte de cabelo", duracao_minutos=30, preco=45.0)
    servico_60 = Servico(nome="Corte + barba", duracao_minutos=60, preco=70.0)
    session.add_all([cliente, barbeiro, servico_30, servico_60])
    session.flush()
    session.add(
        Disponibilidade(
            barbeiro_id=barbeiro.id, dia_semana=0, hora_inicio=time(9, 0), hora_fim=time(18, 0)
        )
    )
    session.commit()
    return Cenario(cliente, barbeiro, servico_30, servico_60)


@pytest.fixture
def notificador() -> NotificadorFalso:
    return NotificadorFalso()


@pytest.fixture
def client(engine: Engine, notificador: NotificadorFalso) -> Iterator[TestClient]:
    fabrica = sessionmaker(bind=engine, expire_on_commit=False)

    def _sessao() -> Iterator[Session]:
        with fabrica() as sessao:
            yield sessao

    app.dependency_overrides[get_db] = _sessao
    app.dependency_overrides[get_agora] = lambda: AGORA_FIXO
    app.dependency_overrides[get_notificador] = lambda: notificador
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def cenario_api(client: TestClient) -> dict[str, int]:
    cliente = client.post(
        "/clientes",
        json={"nome": "Carlos Silva", "email": "carlos@exemplo.com", "telefone": "11987654321"},
    ).json()
    barbeiro = client.post(
        "/barbeiros", json={"nome": "João Barbeiro", "email": "joao@barbearia.com"}
    ).json()
    servico_30 = client.post(
        "/servicos", json={"nome": "Corte de cabelo", "duracao_minutos": 30, "preco": 45.0}
    ).json()
    servico_60 = client.post(
        "/servicos", json={"nome": "Corte + barba", "duracao_minutos": 60, "preco": 70.0}
    ).json()
    client.post(
        f"/barbeiros/{barbeiro['id']}/disponibilidades",
        json={"dia_semana": 0, "hora_inicio": "09:00:00", "hora_fim": "18:00:00"},
    )
    return {
        "cliente_id": cliente["id"],
        "barbeiro_id": barbeiro["id"],
        "servico_30_id": servico_30["id"],
        "servico_60_id": servico_60["id"],
    }
