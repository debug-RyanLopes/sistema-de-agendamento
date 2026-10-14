from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.database import aplicar_migracoes, criar_motor
from app.dependencies import get_agora, get_db, get_notificador
from app.main_admin import criar_app as criar_app_admin
from app.main_cliente import criar_app as criar_app_cliente
from app.models import Barbeiro, Base, Cliente, Disponibilidade, Servico
from tests.conftest import CABECALHO_ADMIN, SENHA_TESTE
from tests.helpers import AGORA_FIXO, NotificadorFalso, na_segunda

TENTATIVAS_POR_APLICACAO = 6


@pytest.fixture
def dois_apps_no_mesmo_arquivo(tmp_path: Path):
    motor = criar_motor(f"sqlite:///{(tmp_path / 'compartilhado.db').as_posix()}")
    Base.metadata.create_all(motor)
    aplicar_migracoes(motor)
    fabrica = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)

    with fabrica() as sessao:
        cliente = Cliente(nome="Carlos Silva", email="carlos@exemplo.com", telefone="11987654321")
        barbeiro = Barbeiro(nome="João Barbeiro", email="joao@barbearia.com")
        servico = Servico(nome="Corte de cabelo", duracao_minutos=30, preco=45.0)
        sessao.add_all([cliente, barbeiro, servico])
        sessao.flush()
        sessao.add(
            Disponibilidade(
                barbeiro_id=barbeiro.id, dia_semana=0, hora_inicio=time(9, 0), hora_fim=time(18, 0)
            )
        )
        sessao.commit()
        ids = {"cliente": cliente.id, "barbeiro": barbeiro.id, "servico": servico.id}

    def _sessao() -> Iterator[Session]:
        with fabrica() as nova:
            yield nova

    notificador = NotificadorFalso()
    aplicacoes = (criar_app_cliente(), criar_app_admin(SENHA_TESTE))
    for aplicacao in aplicacoes:
        aplicacao.dependency_overrides[get_db] = _sessao
        aplicacao.dependency_overrides[get_agora] = lambda: AGORA_FIXO
        aplicacao.dependency_overrides[get_notificador] = lambda: notificador
    yield (
        TestClient(aplicacoes[0]),
        TestClient(aplicacoes[1], headers=CABECALHO_ADMIN),
        ids,
        fabrica,
    )
    motor.dispose()


def test_cliente_e_empresa_disputando_o_mesmo_horario_geram_um_unico_agendamento(
    dois_apps_no_mesmo_arquivo,
):
    publico, admin, ids, fabrica = dois_apps_no_mesmo_arquivo
    inicio = na_segunda(10).isoformat()

    def pelo_cliente(indice: int) -> int:
        return publico.post(
            "/agendamentos",
            json={
                "nome": f"Cliente {indice}",
                "email": f"cliente{indice}@exemplo.com",
                "telefone": "11911112222",
                "barbeiro_id": ids["barbeiro"],
                "servico_id": ids["servico"],
                "inicio": inicio,
            },
        ).status_code

    def pela_empresa(_indice: int) -> int:
        return admin.post(
            "/agendamentos",
            json={
                "cliente_id": ids["cliente"],
                "barbeiro_id": ids["barbeiro"],
                "servico_id": ids["servico"],
                "inicio": inicio,
            },
        ).status_code

    tarefas = [(pelo_cliente, i) for i in range(TENTATIVAS_POR_APLICACAO)] + [
        (pela_empresa, i) for i in range(TENTATIVAS_POR_APLICACAO)
    ]
    with ThreadPoolExecutor(max_workers=len(tarefas)) as pool:
        status = list(pool.map(lambda tarefa: tarefa[0](tarefa[1]), tarefas))

    assert Counter(status) == {201: 1, 409: len(tarefas) - 1}
    assert len(admin.get("/agendamentos").json()) == 1
    with fabrica() as sessao:
        assert sessao.query(Cliente).count() <= 1 + TENTATIVAS_POR_APLICACAO
