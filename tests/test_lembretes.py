"""Lembretes: marca antes de enviar, não repete e não derruba nada se o e-mail falhar."""

from datetime import timedelta

from app.services import lembrete_service
from app.services.lembrete_service import AgendadorDeLembretes, enviar_lembretes
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.helpers import AGORA_FIXO, NotificadorFalso, NotificadorQuebrado, na_segunda


def _agendar(client: TestClient, cenario_api: dict[str, int], inicio) -> dict:
    return client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": inicio.isoformat(),
        },
    ).json()


def test_envia_lembrete_so_para_quem_esta_na_janela_e_uma_vez(
    client: TestClient, cenario_api: dict[str, int], session: Session
):
    proximo = _agendar(client, cenario_api, na_segunda(10))
    _agendar(client, cenario_api, na_segunda(10).replace(day=14))
    cancelado = _agendar(client, cenario_api, na_segunda(12))
    client.delete(f"/agendamentos/{cancelado['id']}")
    notificador = NotificadorFalso()
    agora = na_segunda(10) - timedelta(hours=20)

    enviados = enviar_lembretes(session, notificador, agora, horas=24)
    repetidos = enviar_lembretes(session, notificador, agora, horas=24)

    assert enviados == 1
    assert repetidos == 0
    assert [d.agendamento_id for d in notificador.lembretes] == [proximo["id"]]
    assert notificador.lembretes[0].barbeiro == "João Barbeiro"
    assert notificador.lembretes[0].preco == 45
    marcado = client.get(f"/agendamentos/{proximo['id']}").json()
    assert marcado["status"] == "agendado"


def test_falha_no_envio_nao_repete_o_lembrete(
    client: TestClient, cenario_api: dict[str, int], session: Session, caplog
):
    _agendar(client, cenario_api, na_segunda(10))
    agora = na_segunda(10) - timedelta(hours=1)

    with caplog.at_level("ERROR", logger="notificacoes"):
        primeiro = enviar_lembretes(session, NotificadorQuebrado(), agora, horas=24)
    segundo = enviar_lembretes(session, NotificadorFalso(), agora, horas=24)

    assert primeiro == 1
    assert segundo == 0
    assert "falha ao enviar notificação" in caplog.text


def test_lembretes_desligados_com_zero_horas(session: Session):
    assert enviar_lembretes(session, NotificadorFalso(), AGORA_FIXO, horas=0) == 0


def test_remarcar_reabre_o_lembrete(
    client: TestClient, cenario_api: dict[str, int], session: Session
):
    agendamento = _agendar(client, cenario_api, na_segunda(10))
    agora = na_segunda(10) - timedelta(hours=1)
    enviar_lembretes(session, NotificadorFalso(), agora, horas=24)

    client.post(
        f"/agendamentos/{agendamento['id']}/reagendar", json={"inicio": na_segunda(15).isoformat()}
    )
    notificador = NotificadorFalso()
    enviados = enviar_lembretes(
        session, notificador, na_segunda(15) - timedelta(hours=2), horas=24
    )

    assert enviados == 1
    assert notificador.lembretes[0].inicio == na_segunda(15)


def test_agendador_roda_em_thread_e_para(engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(lembrete_service, "INTERVALO_VERIFICACAO_SEGUNDOS", 0.01)
    chamadas = []
    monkeypatch.setattr(
        lembrete_service, "enviar_lembretes", lambda *args: chamadas.append(args) or 0
    )
    agendador = AgendadorDeLembretes(
        sessionmaker(bind=engine), NotificadorFalso(), lambda: AGORA_FIXO, 24
    )

    agendador.iniciar()
    import time

    limite = time.monotonic() + 2
    while not chamadas and time.monotonic() < limite:
        time.sleep(0.01)
    agendador.parar()

    assert chamadas
    assert not agendador._thread.is_alive()


def test_agendador_desligado_nao_abre_thread(engine):
    from sqlalchemy.orm import sessionmaker

    agendador = AgendadorDeLembretes(
        sessionmaker(bind=engine), NotificadorFalso(), lambda: AGORA_FIXO, 0
    )

    agendador.iniciar()
    agendador.parar()

    assert not agendador._thread.is_alive()
