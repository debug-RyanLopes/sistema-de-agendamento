from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import criar_motor
from app.models import Agendamento, StatusAgendamento
from tests.conftest import Cenario
from tests.test_migracao import _criar_banco_antigo, _migrar

PRIMEIRO = datetime(2030, 1, 7, 9, 0)


def _popular(session: Session, cenario: Cenario, quantidade: int) -> None:
    session.add_all(
        Agendamento(
            cliente_id=cenario.cliente.id,
            barbeiro_id=cenario.barbeiro.id,
            servico_id=cenario.servico_30.id,
            inicio=PRIMEIRO + timedelta(minutes=30 * i),
            fim=PRIMEIRO + timedelta(minutes=30 * i + 30),
            status=StatusAgendamento.AGENDADO,
        )
        for i in range(quantidade)
    )
    session.commit()


def test_sem_parametros_devolve_no_maximo_50_itens_e_o_total(
    client: TestClient, session: Session, cenario: Cenario
):
    _popular(session, cenario, 60)

    pagina = client.get("/agendamentos").json()

    assert len(pagina["itens"]) == 50
    assert pagina["total"] == 60
    assert pagina["limite"] == 50
    assert pagina["deslocamento"] == 0


def test_paginas_seguem_a_ordem_sem_repetir_nem_pular(
    client: TestClient, session: Session, cenario: Cenario
):
    _popular(session, cenario, 25)

    primeira = client.get("/agendamentos", params={"limite": 10, "deslocamento": 0}).json()
    segunda = client.get("/agendamentos", params={"limite": 10, "deslocamento": 10}).json()
    terceira = client.get("/agendamentos", params={"limite": 10, "deslocamento": 20}).json()

    ids = [item["id"] for pag in (primeira, segunda, terceira) for item in pag["itens"]]
    assert len(ids) == 25
    assert len(set(ids)) == 25
    assert len(terceira["itens"]) == 5
    inicios = [item["inicio"] for pag in (primeira, segunda, terceira) for item in pag["itens"]]
    assert inicios == sorted(inicios)


def test_deslocamento_alem_do_fim_devolve_lista_vazia_com_total(
    client: TestClient, session: Session, cenario: Cenario
):
    _popular(session, cenario, 3)

    pagina = client.get("/agendamentos", params={"deslocamento": 100}).json()

    assert pagina["itens"] == []
    assert pagina["total"] == 3


def test_total_respeita_os_filtros(client: TestClient, session: Session, cenario: Cenario):
    _popular(session, cenario, 6)
    primeiro = session.query(Agendamento).order_by(Agendamento.id).first()
    primeiro.status = StatusAgendamento.CANCELADO
    session.commit()

    agendados = client.get("/agendamentos", params={"status": "agendado", "limite": 2}).json()

    assert agendados["total"] == 5
    assert len(agendados["itens"]) == 2


def test_desde_ignora_o_passado(client: TestClient, session: Session, cenario: Cenario):
    _popular(session, cenario, 1)
    session.add(
        Agendamento(
            cliente_id=cenario.cliente.id,
            barbeiro_id=cenario.barbeiro.id,
            servico_id=cenario.servico_30.id,
            inicio=datetime(2029, 12, 1, 10, 0),
            fim=datetime(2029, 12, 1, 10, 30),
            status=StatusAgendamento.AGENDADO,
        )
    )
    session.commit()

    tudo = client.get("/agendamentos").json()
    futuros = client.get("/agendamentos", params={"desde": "2030-01-01"}).json()

    assert tudo["total"] == 2
    assert futuros["total"] == 1
    assert futuros["itens"][0]["inicio"].startswith("2030-01-07")


@pytest.mark.parametrize(
    "parametros",
    [{"limite": 0}, {"limite": 201}, {"limite": -5}, {"deslocamento": -1}, {"limite": "abc"}],
)
def test_parametros_invalidos_sao_recusados(client: TestClient, parametros: dict):
    assert client.get("/agendamentos", params=parametros).status_code == 422


def test_limite_maximo_e_aceito(client: TestClient):
    assert client.get("/agendamentos", params={"limite": 200}).status_code == 200


def test_indice_de_inicio_existe_em_banco_novo_e_migrado(tmp_path: Path):
    for nome in ("novo.db", "antigo.db"):
        url = (
            f"sqlite:///{(tmp_path / nome).as_posix()}"
            if nome == "novo.db"
            else _criar_banco_antigo(tmp_path / nome)
        )
        _migrar(url)

        motor = criar_motor(url)
        with motor.connect() as conexao:
            indices = {
                linha[1] for linha in conexao.exec_driver_sql("PRAGMA index_list(agendamentos)")
            }
        motor.dispose()

        assert "ix_agendamentos_inicio" in indices


def test_consulta_paginada_usa_indice_e_nao_ordena_a_tabela_inteira(
    session: Session, cenario: Cenario
):
    plano = session.connection().exec_driver_sql(
        "EXPLAIN QUERY PLAN SELECT id FROM agendamentos ORDER BY inicio, id LIMIT 50 OFFSET 0"
    )

    texto = " ".join(str(linha) for linha in plano)

    assert "ix_agendamentos_inicio" in texto
    assert "TEMP B-TREE" not in texto
