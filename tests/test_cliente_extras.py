"""Área do cliente: qualquer barbeiro, remarcar, .ics, link mágico e exclusão de dados."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import Cenario
from tests.helpers import AGORA_FIXO, NotificadorFalso, na_segunda


def _corpo(cenario: Cenario, inicio, **extras) -> dict:
    return {
        "nome": "Maria Nova",
        "email": "maria@exemplo.com",
        "telefone": "11911112222",
        "barbeiro_id": cenario.barbeiro.id,
        "servico_id": cenario.servico_30.id,
        "inicio": inicio.isoformat(),
        **extras,
    }


def _marcar(client_publico: TestClient, cenario: Cenario, inicio=None, **extras) -> dict:
    resposta = client_publico.post(
        "/agendamentos", json=_corpo(cenario, inicio or na_segunda(10), **extras)
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _segundo_barbeiro(session: Session) -> int:
    from datetime import time

    from app.models import Barbeiro, Disponibilidade

    pedro = Barbeiro(nome="Pedro Navalha", email="pedro@barbearia.com")
    session.add(pedro)
    session.flush()
    session.add(
        Disponibilidade(barbeiro_id=pedro.id, dia_semana=0, hora_inicio=time(9), hora_fim=time(18))
    )
    session.commit()
    return pedro.id


# --- qualquer barbeiro -------------------------------------------------------------------


def test_sem_barbeiro_escolhe_quem_tem_menos_agenda_no_dia(
    client_publico: TestClient, session: Session, cenario: Cenario
):
    pedro_id = _segundo_barbeiro(session)
    _marcar(client_publico, cenario, na_segunda(9), email="a@exemplo.com")  # João fica com 1

    confirmacao = _marcar(client_publico, cenario, na_segunda(10), barbeiro_id=None)

    assert confirmacao["barbeiro"] == "Pedro Navalha"
    detalhe = session.get(type(cenario.barbeiro), pedro_id)
    assert detalhe.nome == confirmacao["barbeiro"]


def test_sem_barbeiro_so_aceita_horario_livre_em_alguem(
    client_publico: TestClient, cenario: Cenario
):
    _marcar(client_publico, cenario, na_segunda(10), email="a@exemplo.com")

    ocupado = client_publico.post(
        "/agendamentos", json=_corpo(cenario, na_segunda(10), barbeiro_id=None)
    )
    domingo = client_publico.post(
        "/agendamentos", json=_corpo(cenario, na_segunda(10).replace(day=6), barbeiro_id=None)
    )

    assert ocupado.status_code == 422
    assert "nenhum barbeiro" in ocupado.json()["detail"]
    assert domingo.status_code == 422


# --- remarcar -------------------------------------------------------------------------------


def test_cliente_remarca_com_o_codigo(
    client_publico: TestClient, cenario: Cenario, notificador: NotificadorFalso
):
    confirmacao = _marcar(client_publico, cenario)

    resposta = client_publico.post(
        f"/agendamentos/{confirmacao['id']}/reagendar",
        json={"codigo": confirmacao["codigo_cancelamento"], "inicio": na_segunda(15).isoformat()},
    )

    assert resposta.status_code == 200
    assert resposta.json()["id"] == confirmacao["id"]
    assert resposta.json()["inicio"] == na_segunda(15).isoformat()
    assert resposta.json()["codigo_cancelamento"] == confirmacao["codigo_cancelamento"]
    assert len(notificador.enviados) == 2
    livre = client_publico.get(
        "/disponibilidade", params={"data": "2030-01-07", "servico_id": cenario.servico_30.id}
    ).json()
    assert na_segunda(10).isoformat() in livre["barbeiros"][0]["horarios"]


def test_remarcar_com_codigo_errado_ou_fora_do_mes(client_publico: TestClient, cenario: Cenario):
    confirmacao = _marcar(client_publico, cenario)

    errado = client_publico.post(
        f"/agendamentos/{confirmacao['id']}/reagendar",
        json={"codigo": "errado", "inicio": na_segunda(15).isoformat()},
    )
    fora_do_mes = client_publico.post(
        f"/agendamentos/{confirmacao['id']}/reagendar",
        json={"codigo": confirmacao["codigo_cancelamento"], "inicio": "2030-02-04T10:00:00"},
    )
    inexistente = client_publico.post(
        "/agendamentos/999/reagendar", json={"codigo": "x", "inicio": na_segunda(15).isoformat()}
    )

    assert errado.status_code == 404
    assert fora_do_mes.status_code == 422
    assert inexistente.status_code == 404
    assert (
        client_publico.get(
            f"/agendamentos/{confirmacao['id']}/ics",
            params={"codigo": confirmacao["codigo_cancelamento"]},
        ).text.count("DTSTART")
        == 1
    )


# --- .ics ------------------------------------------------------------------------------------


def test_ics_descreve_o_evento_no_fuso_da_barbearia(client_publico: TestClient, cenario: Cenario):
    confirmacao = _marcar(client_publico, cenario)

    resposta = client_publico.get(
        f"/agendamentos/{confirmacao['id']}/ics",
        params={"codigo": confirmacao["codigo_cancelamento"]},
    )
    errado = client_publico.get(f"/agendamentos/{confirmacao['id']}/ics", params={"codigo": "x"})

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/calendar")
    assert "attachment" in resposta.headers["content-disposition"]
    assert "DTSTART;TZID=America/Manaus:20300107T100000" in resposta.text
    assert "DTEND;TZID=America/Manaus:20300107T103000" in resposta.text
    assert "SUMMARY:Corte de cabelo com João Barbeiro" in resposta.text
    assert resposta.text.endswith("END:VCALENDAR\r\n")
    assert errado.status_code == 404


def test_ics_escapa_caracteres_especiais():
    from decimal import Decimal

    from app.calendario import gerar_ics
    from app.services.notificacao_service import DadosAgendamento

    dados = DadosAgendamento(
        email="a@b.com",
        cliente="A",
        barbeiro="João; Filho",
        servico="Corte, barba\nbigode",
        inicio=na_segunda(10),
        preco=Decimal("45.00"),
        agendamento_id=7,
    )

    ics = gerar_ics(dados, na_segunda(10, 30), "America/Manaus", AGORA_FIXO)

    assert "SUMMARY:Corte\\, barba\\nbigode com João\; Filho" in ics
    assert "UID:agendamento-7@barbearia" in ics


# --- link mágico ----------------------------------------------------------------------------


def _pedir_token(client_publico: TestClient, notificador: NotificadorFalso, email: str) -> str:
    resposta = client_publico.post("/meus-agendamentos/solicitar", json={"email": email})
    assert resposta.status_code == 202
    _, _, url = notificador.links[-1]
    return url.split("token=")[1]


def test_link_magico_lista_e_cancela_os_proprios_agendamentos(
    client_publico: TestClient, cenario: Cenario, notificador: NotificadorFalso
):
    confirmacao = _marcar(client_publico, cenario)
    _marcar(client_publico, cenario, na_segunda(12), email="outra@exemplo.com")
    token = _pedir_token(client_publico, notificador, "maria@exemplo.com")

    meus = client_publico.get("/meus-agendamentos", params={"token": token})

    assert meus.status_code == 200
    assert meus.json()["email"] == "maria@exemplo.com"
    assert [item["id"] for item in meus.json()["agendamentos"]] == [confirmacao["id"]]
    assert (
        meus.json()["agendamentos"][0]["codigo_cancelamento"] == confirmacao["codigo_cancelamento"]
    )
    assert notificador.links[-1][0] == "maria@exemplo.com"
    assert "Seus agendamentos" == notificador.links[-1][1]


def test_pedido_de_link_para_email_desconhecido_responde_igual_e_nao_envia(
    client_publico: TestClient, notificador: NotificadorFalso
):
    resposta = client_publico.post("/meus-agendamentos/solicitar", json={"email": "ninguem@x.com"})

    assert resposta.status_code == 202
    assert notificador.links == []


def test_token_invalido_ou_de_outra_finalidade_retorna_404(
    client_publico: TestClient, cenario: Cenario
):
    from app.config import CONFIG
    from app.services import auth_service

    outro = auth_service.gerar_token(CONFIG.secret_key, "sessao", "maria@exemplo.com", 60)

    assert client_publico.get("/meus-agendamentos", params={"token": "lixo"}).status_code == 404
    assert client_publico.get("/meus-agendamentos", params={"token": outro}).status_code == 404


def test_cliente_apaga_os_proprios_dados_so_sem_agendamentos_futuros(
    client_publico: TestClient,
    client: TestClient,
    cenario: Cenario,
    notificador: NotificadorFalso,
):
    confirmacao = _marcar(client_publico, cenario)
    token = _pedir_token(client_publico, notificador, "maria@exemplo.com")

    com_futuro = client_publico.post("/meus-dados/exclusao", params={"token": token})
    client_publico.post(
        f"/agendamentos/{confirmacao['id']}/cancelar",
        json={"codigo": confirmacao["codigo_cancelamento"]},
    )
    apagado = client_publico.post("/meus-dados/exclusao", params={"token": token})
    de_novo = client_publico.post("/meus-dados/exclusao", params={"token": token})

    assert com_futuro.status_code == 409
    assert apagado.status_code == 204
    assert de_novo.status_code == 404  # o e-mail não existe mais
    clientes = client.get(
        "/clientes", params={"incluir_inativos": True, "busca": "removido"}
    ).json()
    assert clientes[0]["nome"] == "Cliente removido"
    assert clientes[0]["telefone"] == "0000000000"
    assert clientes[0]["ativo"] is False
    assert clientes[0]["anonimizado_em"] is not None
    assert client.get(f"/agendamentos/{confirmacao['id']}").status_code == 200  # histórico fica


def test_configuracao_e_saude_sao_publicas(client_publico: TestClient):
    configuracao = client_publico.get("/configuracao").json()
    saude = client_publico.get("/saude")

    assert configuracao["fuso"] == "America/Manaus"
    assert configuracao["slot_minutos"] == 15
    assert configuracao["max_agendamentos_ativos_por_cliente"] == 3
    assert saude.status_code == 200
    assert saude.json()["banco"] == "ok"
