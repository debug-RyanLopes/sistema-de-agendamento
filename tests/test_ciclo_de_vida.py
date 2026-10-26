"""Status do agendamento: cancelar só o futuro; concluir ou registrar falta só o passado."""

from fastapi.testclient import TestClient

from tests.helpers import AGORA_FIXO, NotificadorFalso, na_segunda

PASSADO = AGORA_FIXO.replace(day=1, hour=7)  # 01/01/2030 07:00, antes do AGORA_FIXO (08:00)


def _agendar(client: TestClient, cenario_api: dict[str, int], inicio=None):
    return client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": (inicio or na_segunda(10)).isoformat(),
        },
    )


def _agendar_no_passado(client: TestClient, cenario_api: dict[str, int], session) -> int:
    """Agendamento que já aconteceu: só dá para inserir direto no banco."""
    from app.models import Agendamento, StatusAgendamento

    agendamento = Agendamento(
        cliente_id=cenario_api["cliente_id"],
        barbeiro_id=cenario_api["barbeiro_id"],
        servico_id=cenario_api["servico_30_id"],
        inicio=PASSADO,
        fim=PASSADO.replace(minute=30),
        status=StatusAgendamento.AGENDADO,
    )
    session.add(agendamento)
    session.commit()
    return agendamento.id


def test_agendamento_nasce_com_origem_e_data_de_criacao(
    client: TestClient, client_publico: TestClient, cenario_api: dict[str, int]
):
    pela_empresa = _agendar(client, cenario_api).json()
    pelo_cliente = client_publico.post(
        "/agendamentos",
        json={
            "nome": "Maria",
            "email": "maria@exemplo.com",
            "telefone": "92991112222",
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": na_segunda(11).isoformat(),
        },
    ).json()

    assert pela_empresa["origem"] == "empresa"
    assert pela_empresa["criado_em"] == AGORA_FIXO.isoformat()
    detalhe = client.get(f"/agendamentos/{pelo_cliente['id']}").json()
    assert detalhe["origem"] == "cliente"


def test_empresa_cancela_futuro_com_motivo_e_cliente_e_avisado(
    client: TestClient, cenario_api: dict[str, int], notificador: NotificadorFalso
):
    agendamento = _agendar(client, cenario_api).json()

    resposta = client.delete(f"/agendamentos/{agendamento['id']}", params={"motivo": "chuva"})

    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["status"] == "cancelado"
    assert corpo["cancelado_por"] == "empresa"
    assert corpo["cancelado_em"] == AGORA_FIXO.isoformat()
    assert corpo["motivo_cancelamento"] == "chuva"
    assert len(notificador.cancelamentos) == 1
    assert notificador.cancelamentos[0].email == "carlos@exemplo.com"


def test_cancelar_duas_vezes_nao_avisa_duas_vezes(
    client: TestClient, cenario_api: dict[str, int], notificador: NotificadorFalso
):
    agendamento = _agendar(client, cenario_api).json()
    client.delete(f"/agendamentos/{agendamento['id']}")

    repetido = client.delete(f"/agendamentos/{agendamento['id']}")

    assert repetido.status_code == 200
    assert len(notificador.cancelamentos) == 1


def test_empresa_nao_cancela_horario_que_ja_passou(
    client: TestClient, cenario_api: dict[str, int], session
):
    identificador = _agendar_no_passado(client, cenario_api, session)

    resposta = client.delete(f"/agendamentos/{identificador}")

    assert resposta.status_code == 422
    assert "concluído ou falta" in resposta.json()["detail"]
    assert client.get(f"/agendamentos/{identificador}").json()["status"] == "agendado"


def test_marca_atendimento_passado_como_concluido_ou_falta(
    client: TestClient, cenario_api: dict[str, int], session
):
    concluido_id = _agendar_no_passado(client, cenario_api, session)
    falta_id = _agendar_no_passado(client, cenario_api, session)

    concluido = client.patch(f"/agendamentos/{concluido_id}/status", json={"status": "concluido"})
    falta = client.patch(f"/agendamentos/{falta_id}/status", json={"status": "nao_compareceu"})

    assert concluido.json()["status"] == "concluido"
    assert falta.json()["status"] == "nao_compareceu"
    impacto = client.get(f"/barbeiros/{cenario_api['barbeiro_id']}/impacto-desativacao").json()
    assert impacto["atendimentos_realizados"] == 1
    assert impacto["faltas"] == 1


def test_marcar_status_e_idempotente_e_nao_volta_atras(
    client: TestClient, cenario_api: dict[str, int], session
):
    identificador = _agendar_no_passado(client, cenario_api, session)
    client.patch(f"/agendamentos/{identificador}/status", json={"status": "concluido"})

    repetido = client.patch(f"/agendamentos/{identificador}/status", json={"status": "concluido"})
    mudanca = client.patch(
        f"/agendamentos/{identificador}/status", json={"status": "nao_compareceu"}
    )
    cancelar = client.delete(f"/agendamentos/{identificador}")

    assert repetido.status_code == 200
    assert mudanca.status_code == 409
    assert cancelar.status_code == 409


def test_nao_conclui_atendimento_futuro_nem_aceita_status_de_cancelamento(
    client: TestClient, cenario_api: dict[str, int]
):
    agendamento = _agendar(client, cenario_api).json()

    futuro = client.patch(
        f"/agendamentos/{agendamento['id']}/status", json={"status": "concluido"}
    )
    invalido = client.patch(
        f"/agendamentos/{agendamento['id']}/status", json={"status": "cancelado"}
    )
    inexistente = client.patch("/agendamentos/999/status", json={"status": "concluido"})

    assert futuro.status_code == 409
    assert "ainda não aconteceu" in futuro.json()["detail"]
    assert invalido.status_code == 409
    assert inexistente.status_code == 404


def test_agendado_que_ja_passou_sem_marcacao_conta_como_realizado(
    client: TestClient, cenario_api: dict[str, int], session
):
    _agendar_no_passado(client, cenario_api, session)

    impacto = client.get(f"/barbeiros/{cenario_api['barbeiro_id']}/impacto-desativacao").json()

    assert impacto["atendimentos_realizados"] == 1
    assert impacto["faltas"] == 0


def test_filtra_pelos_novos_status(client: TestClient, cenario_api: dict[str, int], session):
    identificador = _agendar_no_passado(client, cenario_api, session)
    client.patch(f"/agendamentos/{identificador}/status", json={"status": "nao_compareceu"})
    _agendar(client, cenario_api)

    faltas = client.get("/agendamentos", params={"status": "nao_compareceu"}).json()
    ate = client.get("/agendamentos", params={"ate": "2030-01-01"}).json()

    assert [item["id"] for item in faltas["itens"]] == [identificador]
    assert ate["total"] == 1


def test_empresa_remarca_e_o_horario_antigo_fica_livre(
    client: TestClient, cenario_api: dict[str, int], notificador: NotificadorFalso
):
    agendamento = _agendar(client, cenario_api).json()

    resposta = client.post(
        f"/agendamentos/{agendamento['id']}/reagendar", json={"inicio": na_segunda(14).isoformat()}
    )

    assert resposta.status_code == 200
    assert resposta.json()["inicio"] == na_segunda(14).isoformat()
    assert resposta.json()["fim"] == na_segunda(14, 30).isoformat()
    assert _agendar(client, cenario_api).status_code == 201  # 10:00 voltou a ficar livre
    assert len(notificador.enviados) == 3  # duas marcações + a confirmação da remarcação


def test_remarcar_respeita_conflito_passado_e_status(
    client: TestClient, cenario_api: dict[str, int], session
):
    primeiro = _agendar(client, cenario_api).json()
    segundo = _agendar(client, cenario_api, na_segunda(11)).json()
    passado = _agendar_no_passado(client, cenario_api, session)
    client.delete(f"/agendamentos/{segundo['id']}")

    conflito = client.post(
        f"/agendamentos/{primeiro['id']}/reagendar",
        json={"inicio": na_segunda(10, 15).isoformat()},
    )
    mesmo_horario = client.post(
        f"/agendamentos/{primeiro['id']}/reagendar", json={"inicio": na_segunda(10).isoformat()}
    )
    para_o_passado = client.post(
        f"/agendamentos/{primeiro['id']}/reagendar", json={"inicio": PASSADO.isoformat()}
    )
    cancelado = client.post(
        f"/agendamentos/{segundo['id']}/reagendar", json={"inicio": na_segunda(15).isoformat()}
    )
    ja_passou = client.post(
        f"/agendamentos/{passado}/reagendar", json={"inicio": na_segunda(15).isoformat()}
    )

    assert conflito.status_code == 200  # 10:15 só sobrepõe a si mesmo
    assert mesmo_horario.status_code == 200
    assert para_o_passado.status_code == 422
    assert cancelado.status_code == 409
    assert ja_passou.status_code == 422
