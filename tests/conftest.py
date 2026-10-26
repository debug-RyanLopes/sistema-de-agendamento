import base64
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import time

import pytest
from app.dependencies import get_agora, get_db, get_notificador
from app.main_admin import criar_app as criar_app_admin
from app.main_cliente import criar_app as criar_app_cliente
from app.models import Barbeiro, Base, Cliente, Disponibilidade, Servico
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.helpers import AGORA_FIXO, NotificadorFalso

SENHA_TESTE = "senha-de-teste"
CABECALHO_ADMIN = {
    "Authorization": "Basic " + base64.b64encode(f"admin:{SENHA_TESTE}".encode()).decode()
}


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


def configurar_dependencias(
    aplicacao: FastAPI, engine: Engine, notificador: NotificadorFalso
) -> FastAPI:
    fabrica = sessionmaker(bind=engine, expire_on_commit=False)

    def _sessao() -> Iterator[Session]:
        with fabrica() as sessao:
            yield sessao

    aplicacao.dependency_overrides[get_db] = _sessao
    aplicacao.dependency_overrides[get_agora] = lambda: AGORA_FIXO
    aplicacao.dependency_overrides[get_notificador] = lambda: notificador
    return aplicacao


@pytest.fixture
def app_admin(engine: Engine, notificador: NotificadorFalso) -> FastAPI:
    return configurar_dependencias(criar_app_admin(SENHA_TESTE), engine, notificador)


@pytest.fixture
def app_publico(engine: Engine, notificador: NotificadorFalso) -> FastAPI:
    return configurar_dependencias(criar_app_cliente(), engine, notificador)


@pytest.fixture
def client(app_admin: FastAPI) -> TestClient:
    return TestClient(app_admin, headers=CABECALHO_ADMIN)


@pytest.fixture
def client_publico(app_publico: FastAPI) -> TestClient:
    return TestClient(app_publico)


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
