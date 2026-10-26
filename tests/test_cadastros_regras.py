from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.database import criar_motor
from app.models import Barbeiro, Servico
from app.schemas import AgendamentoIn
from app.services import agendamento_service, barbeiro_service
from app.tempo import agora_local
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import Cenario
from tests.helpers import AGORA_FIXO, na_segunda
from tests.test_migracao import _criar_banco_antigo, _migrar

CLIENTE = {"nome": "Ana Souza", "email": "ana@exemplo.com", "telefone": "11999998888"}


def test_cliente_com_email_repetido_recebe_409(client: TestClient):
    client.post("/clientes", json=CLIENTE)

    repetido = client.post("/clientes", json={**CLIENTE, "nome": "Outra Ana"})

    assert repetido.status_code == 409
    assert "ana@exemplo.com" in repetido.json()["detail"]
    assert len(client.get("/clientes").json()) == 1


def test_email_repetido_ignora_maiusculas_e_espacos(client: TestClient):
    client.post("/clientes", json=CLIENTE)

    repetido = client.post("/clientes", json={**CLIENTE, "email": "  ANA@Exemplo.com "})

    assert repetido.status_code == 409


def test_editar_para_email_de_outro_cliente_recebe_409(client: TestClient):
    client.post("/clientes", json=CLIENTE)
    outro = client.post(
        "/clientes", json={**CLIENTE, "nome": "Bia Lima", "email": "bia@exemplo.com"}
    ).json()

    resposta = client.put(f"/clientes/{outro['id']}", json={**CLIENTE, "nome": "Bia Lima"})

    assert resposta.status_code == 409


def test_editar_mantendo_o_proprio_email_e_permitido(client: TestClient):
    criado = client.post("/clientes", json=CLIENTE).json()

    resposta = client.put(f"/clientes/{criado['id']}", json={**CLIENTE, "nome": "Ana Maria"})

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Ana Maria"


def test_barbeiros_podem_repetir_email(client: TestClient):
    barbeiro = {"nome": "João Barbeiro", "email": "joao@barbearia.com"}

    assert client.post("/barbeiros", json=barbeiro).status_code == 201
    assert client.post("/barbeiros", json=barbeiro).status_code == 201


def test_indice_unico_e_criado_no_banco_migrado(tmp_path: Path):
    url = _criar_banco_antigo(tmp_path / "antigo.db")

    _migrar(url)

    motor = criar_motor(url)
    with motor.connect() as conexao:
        lista = conexao.exec_driver_sql("PRAGMA index_list(clientes)")
        indices = {linha[1]: linha[2] for linha in lista}
    motor.dispose()
    assert indices["uq_clientes_email"] == 1


def test_migracao_com_emails_repetidos_nao_quebra_e_avisa(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    url = _criar_banco_antigo(tmp_path / "antigo.db")
    motor = criar_motor(url)
    with motor.begin() as conexao:
        conexao.exec_driver_sql(
            "INSERT INTO clientes VALUES"
            " (2, 'Carlos Repetido', 'carlos@exemplo.com', '11900000000')"
        )
    motor.dispose()

    with caplog.at_level("WARNING"):
        _migrar(url)

    assert "e-mail repetido" in caplog.text


@pytest.mark.parametrize("preco", ["abc", -1, "10.005", 0.1 + 0.2, "12345678901.00"])
def test_preco_invalido_e_rejeitado(client: TestClient, preco):
    resposta = client.post(
        "/servicos", json={"nome": "Corte", "duracao_minutos": 30, "preco": preco}
    )

    assert resposta.status_code == 422


@pytest.mark.parametrize(
    ("enviado", "esperado"), [("45", "45.00"), (45, "45.00"), (35.9, "35.90"), ("0", "0.00")]
)
def test_preco_e_sempre_devolvido_com_duas_casas(client: TestClient, enviado, esperado: str):
    resposta = client.post(
        "/servicos", json={"nome": "Corte", "duracao_minutos": 30, "preco": enviado}
    )

    assert resposta.status_code == 201
    assert resposta.json()["preco"] == esperado


def test_preco_no_banco_volta_como_decimal_exato(session: Session):
    servico = Servico(nome="Corte", duracao_minutos=30, preco=Decimal("19.99"))
    session.add(servico)
    session.commit()
    session.expire_all()

    recarregado = session.get(Servico, servico.id)

    assert recarregado.preco == Decimal("19.99")
    assert isinstance(recarregado.preco, Decimal)


def test_somar_precos_nao_acumula_erro_de_float(session: Session):
    session.add_all(
        [Servico(nome=f"S{i}", duracao_minutos=5, preco=Decimal("0.10")) for i in range(3)]
    )
    session.commit()

    total = sum(servico.preco for servico in session.query(Servico).all())

    assert total == Decimal("0.30")


def test_preco_legado_em_float_e_lido_como_decimal(tmp_path: Path):
    url = _criar_banco_antigo(tmp_path / "antigo.db")
    _migrar(url)

    motor = criar_motor(url)
    with Session(motor) as sessao:
        assert sessao.get(Servico, 1).preco == Decimal("45.00")
    motor.dispose()


def test_confirmacao_do_cliente_traz_o_valor_como_texto(
    client_publico: TestClient, cenario: Cenario
):
    resposta = client_publico.post(
        "/agendamentos",
        json={
            "nome": "Maria Nova",
            "email": "maria@exemplo.com",
            "telefone": "11911112222",
            "barbeiro_id": cenario.barbeiro.id,
            "servico_id": cenario.servico_30.id,
            "inicio": "2030-01-07T10:00:00",
        },
    )

    assert resposta.json()["preco"] == "45.00"


def _agendar(session: Session, cenario: Cenario, inicio: datetime, servico=None) -> None:
    agendamento_service.criar(
        session,
        AgendamentoIn(
            cliente_id=cenario.cliente.id,
            barbeiro_id=cenario.barbeiro.id,
            servico_id=(servico or cenario.servico_30).id,
            inicio=inicio,
        ),
        AGORA_FIXO,
    )


def test_impacto_sem_agendamentos(session: Session, cenario: Cenario):
    impacto = barbeiro_service.impacto_desativacao(session, cenario.barbeiro.id, AGORA_FIXO)

    assert impacto.total_futuros == 0
    assert impacto.valor_futuro == Decimal("0.00")
    assert impacto.proximo_atendimento is None
    assert impacto.agendamentos_futuros == []
    assert impacto.atendimentos_realizados == 0


def test_impacto_lista_futuros_soma_valor_e_aponta_o_proximo(session: Session, cenario: Cenario):
    _agendar(session, cenario, na_segunda(14))
    _agendar(session, cenario, na_segunda(10))
    _agendar(session, cenario, na_segunda(15), cenario.servico_60)

    impacto = barbeiro_service.impacto_desativacao(session, cenario.barbeiro.id, AGORA_FIXO)

    assert impacto.total_futuros == 3
    assert impacto.valor_futuro == Decimal("160.00")
    assert impacto.proximo_atendimento == na_segunda(10)
    assert [item.inicio for item in impacto.agendamentos_futuros] == [
        na_segunda(10),
        na_segunda(14),
        na_segunda(15),
    ]
    assert impacto.agendamentos_futuros[0].cliente == "Carlos Silva"
    assert impacto.agendamentos_futuros[2].servico == "Corte + barba"


def test_impacto_ignora_cancelados(session: Session, cenario: Cenario):
    _agendar(session, cenario, na_segunda(10))
    cancelado = agendamento_service.listar(session)[0]
    agendamento_service.cancelar(session, cancelado.id)

    impacto = barbeiro_service.impacto_desativacao(session, cenario.barbeiro.id, AGORA_FIXO)

    assert impacto.total_futuros == 0


def test_impacto_conta_atendimentos_ja_realizados(session: Session, cenario: Cenario):
    _agendar(session, cenario, na_segunda(10))
    _agendar(session, cenario, na_segunda(14))
    depois_das_11 = na_segunda(11)

    impacto = barbeiro_service.impacto_desativacao(session, cenario.barbeiro.id, depois_das_11)

    assert impacto.atendimentos_realizados == 1
    assert impacto.total_futuros == 1


def test_impacto_calcula_tempo_na_empresa(session: Session, cenario: Cenario):
    cenario.barbeiro.criado_em = AGORA_FIXO - timedelta(days=400)
    session.commit()

    impacto = barbeiro_service.impacto_desativacao(session, cenario.barbeiro.id, AGORA_FIXO)

    assert impacto.dias_na_empresa == 400
    assert impacto.cadastrado_em == AGORA_FIXO - timedelta(days=400)


def test_impacto_sem_data_de_cadastro_nao_inventa_tempo(session: Session, cenario: Cenario):
    cenario.barbeiro.criado_em = None
    session.commit()

    impacto = barbeiro_service.impacto_desativacao(session, cenario.barbeiro.id, AGORA_FIXO)

    assert impacto.dias_na_empresa is None
    assert impacto.cadastrado_em is None


def test_impacto_nao_considera_agendamentos_de_outro_barbeiro(session: Session, cenario: Cenario):
    _agendar(session, cenario, na_segunda(10))
    outro = Barbeiro(nome="Pedro Navalha", email="pedro@barbearia.com")
    session.add(outro)
    session.commit()

    impacto = barbeiro_service.impacto_desativacao(session, outro.id, AGORA_FIXO)

    assert impacto.total_futuros == 0


def test_barbeiro_novo_registra_a_data_de_cadastro(client: TestClient):
    criado = client.post("/barbeiros", json={"nome": "Pedro", "email": "p@barbearia.com"}).json()

    impacto = client.get(f"/barbeiros/{criado['id']}/impacto-desativacao").json()

    assert impacto["cadastrado_em"] is not None
    assert abs(datetime.fromisoformat(impacto["cadastrado_em"]) - agora_local()) < timedelta(
        seconds=10
    )


def test_api_do_impacto_devolve_404_para_barbeiro_inexistente(client: TestClient):
    assert client.get("/barbeiros/999/impacto-desativacao").status_code == 404


def test_api_do_impacto_lista_agendamentos_futuros(
    client: TestClient, cenario_api: dict[str, int]
):
    client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": "2030-01-07T10:00:00",
        },
    )

    impacto = client.get(f"/barbeiros/{cenario_api['barbeiro_id']}/impacto-desativacao").json()

    assert impacto["total_futuros"] == 1
    assert impacto["valor_futuro"] == "45.00"
    assert impacto["agendamentos_futuros"][0]["cliente"] == "Carlos Silva"


def test_impacto_nao_existe_na_area_do_cliente(client_publico: TestClient):
    assert client_publico.get("/barbeiros/1/impacto-desativacao").status_code == 404


@pytest.mark.parametrize(
    ("digitado", "guardado"),
    [
        ("(92) 91234-5678", "92912345678"),
        ("92 91234 5678", "92912345678"),
        ("9291234-1234", "92912341234"),
        ("92912345678", "92912345678"),
        ("(92) 3234-5678", "9232345678"),
    ],
)
def test_telefone_valido_e_guardado_so_com_digitos(
    client: TestClient, digitado: str, guardado: str
):
    resposta = client.post("/clientes", json={**CLIENTE, "telefone": digitado})

    assert resposta.status_code == 201
    assert resposta.json()["telefone"] == guardado


@pytest.mark.parametrize(
    "telefone",
    [
        "123",
        "abcdefghij",
        "9212345678",  # fixo não começa com 9
        "92812345678",  # celular sem 9 depois do DDD
        "0292345678",  # DDD começando com 0
        "929123456789",  # 12 dígitos
        "(92) 9123-45x8",
    ],
)
def test_telefone_invalido_e_recusado(client: TestClient, telefone: str):
    resposta = client.post("/clientes", json={**CLIENTE, "telefone": telefone})

    assert resposta.status_code == 422


def test_cliente_publico_tambem_tem_o_telefone_validado(
    client_publico: TestClient, cenario: Cenario
):
    corpo = {
        "nome": "Maria Nova",
        "email": "maria@exemplo.com",
        "telefone": "(92) 91234-5678",
        "barbeiro_id": cenario.barbeiro.id,
        "servico_id": cenario.servico_30.id,
        "inicio": "2030-01-07T10:00:00",
    }

    invalido = client_publico.post("/agendamentos", json={**corpo, "telefone": "12345"})
    valido = client_publico.post("/agendamentos", json=corpo)

    assert invalido.status_code == 422
    assert valido.status_code == 201
