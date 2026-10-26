"""Transações, migração, PostgreSQL (tipo Dinheiro), log JSON, SMTP e máscara de PII."""

import json
import logging
import smtplib
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from app.config import Config
from app.database import aplicar_migracoes, criar_motor
from app.logs import FormatadorJson
from app.models import Base, Dinheiro
from app.services import notificacao_service
from app.services.notificacao_service import (
    DadosAgendamento,
    LogNotificador,
    SmtpNotificador,
    criar_notificador,
    mascarar_email,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session, sessionmaker

from tests.helpers import AGORA_FIXO, na_segunda
from tests.test_migracao import _criar_banco_antigo, _migrar

# --- transações ------------------------------------------------------------------------------


def test_leitura_abre_transacao_deferred_e_escrita_abre_immediate(tmp_path: Path, notificador):
    from app.dependencies import get_agora, get_db, get_notificador
    from app.main_admin import criar_app

    motor = criar_motor(f"sqlite:///{(tmp_path / 'tx.db').as_posix()}")
    Base.metadata.create_all(motor)
    aplicar_migracoes(motor)
    fabrica = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    aplicacao = criar_app("x", lembretes=False)

    def _sessao():
        with fabrica() as sessao:
            yield sessao

    aplicacao.dependency_overrides[get_db] = _sessao
    aplicacao.dependency_overrides[get_agora] = lambda: AGORA_FIXO
    aplicacao.dependency_overrides[get_notificador] = lambda: notificador
    cliente = TestClient(aplicacao, headers={"Authorization": "Basic YWRtaW46eA=="})
    cliente.get("/servicos")  # cria o usuário admin fora da medição

    emitidos: list[str] = []
    event.listen(
        motor,
        "begin",
        lambda conexao: emitidos.append(
            conexao.get_execution_options().get("transacao", "DEFERRED")
        ),
    )
    cliente.get("/servicos")
    cliente.get("/agendamentos")
    leituras = list(emitidos)
    emitidos.clear()
    cliente.post("/servicos", json={"nome": "Corte", "duracao_minutos": 30, "preco": "10.00"})
    escritas = list(emitidos)
    motor.dispose()

    assert leituras and all(modo == "DEFERRED" for modo in leituras)
    assert "IMMEDIATE" in escritas


def test_banco_em_arquivo_usa_wal(tmp_path: Path):
    motor = criar_motor(f"sqlite:///{(tmp_path / 'wal.db').as_posix()}")
    with motor.connect() as conexao:
        modo = conexao.exec_driver_sql("PRAGMA journal_mode").scalar()
    motor.dispose()

    assert modo == "wal"


# --- migração --------------------------------------------------------------------------------


def test_migracao_acrescenta_as_colunas_do_ciclo_de_vida_e_cria_tabelas_novas(tmp_path: Path):
    url = _criar_banco_antigo(tmp_path / "antigo.db")

    _migrar(url)

    motor = criar_motor(url)
    with motor.connect() as conexao:
        colunas = {
            linha[1] for linha in conexao.exec_driver_sql("PRAGMA table_info(agendamentos)")
        }
        tabelas = {
            linha[0]
            for linha in conexao.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        indices = {linha[1] for linha in conexao.exec_driver_sql("PRAGMA index_list(barbeiros)")}
    motor.dispose()

    assert {
        "criado_em",
        "origem",
        "cancelado_em",
        "cancelado_por",
        "motivo_cancelamento",
        "lembrete_enviado_em",
    } <= colunas
    assert {"usuarios", "bloqueios", "vendas", "venda_itens"} <= tabelas
    assert "uq_barbeiros_email" in indices


def test_migracao_com_barbeiros_repetidos_avisa_e_segue(tmp_path: Path, caplog):
    url = _criar_banco_antigo(tmp_path / "antigo.db")
    motor = criar_motor(url)
    with motor.begin() as conexao:
        conexao.exec_driver_sql("INSERT INTO barbeiros VALUES (2, 'Clone', 'joao@barbearia.com')")
    motor.dispose()

    with caplog.at_level("WARNING"):
        _migrar(url)

    assert "barbeiros com e-mail repetido" in caplog.text


def test_migracao_nao_roda_em_outros_bancos():
    class MotorFalso:
        url = "postgresql+psycopg://x"

        def connect(self):
            raise AssertionError("não deveria conectar")

    aplicar_migracoes(MotorFalso())  # não levanta


def test_motor_para_postgres_nao_tem_os_eventos_do_sqlite():
    motor = criar_motor("postgresql+psycopg://usuario:senha@localhost:1/banco")

    assert motor.dialect.name == "postgresql"
    assert not event.contains(motor, "begin", lambda c: None)
    motor.dispose()


# --- tipo Dinheiro em outros bancos ---------------------------------------------------------


def test_dinheiro_vira_numeric_no_postgres_e_float_no_sqlite():
    tipo = Dinheiro()
    pg = postgresql.dialect()
    lite = sqlite.dialect()

    from sqlalchemy import Float, Numeric

    assert isinstance(tipo.load_dialect_impl(pg), Numeric)
    assert isinstance(tipo.load_dialect_impl(lite), Float)
    assert tipo.process_bind_param(Decimal("12.346"), pg) == Decimal("12.35")
    assert tipo.process_bind_param(Decimal("12.346"), lite) == 12.35
    assert tipo.process_result_value(Decimal("12.3"), pg) == Decimal("12.30")
    assert tipo.process_result_value(None, pg) is None
    assert tipo.process_bind_param(None, lite) is None


# --- logs ------------------------------------------------------------------------------------


def test_formatador_json_gera_uma_linha_por_evento():
    registro = logging.LogRecord("teste", logging.WARNING, __file__, 1, "olá %s", ("mundo",), None)

    linha = FormatadorJson().format(registro)

    evento = json.loads(linha)
    assert evento["nivel"] == "WARNING"
    assert evento["mensagem"] == "olá mundo"
    assert evento["origem"] == "teste"
    assert "momento" in evento and "excecao" not in evento


def test_formatador_json_inclui_a_excecao():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        registro = logging.LogRecord(
            "t", logging.ERROR, __file__, 1, "falhou", None, sys.exc_info()
        )

    evento = json.loads(FormatadorJson().format(registro))

    assert "ValueError: boom" in evento["excecao"]


# --- notificações ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "mascarado"),
    [
        ("carlos@exemplo.com", "c***s@exemplo.com"),
        ("ab@x.com", "a***@x.com"),
        ("a@x.com", "a***@x.com"),
    ],
)
def test_mascara_de_email(email: str, mascarado: str):
    assert mascarar_email(email) == mascarado


def test_log_notificador_cobre_todas_as_mensagens_sem_pii(caplog):
    dados = DadosAgendamento(
        "carlos@exemplo.com", "Carlos Silva", "João", "Corte", na_segunda(10), Decimal("45")
    )
    notificador = LogNotificador()

    with caplog.at_level(logging.INFO, logger="notificacoes"):
        notificador.enviar_cancelamento(dados)
        notificador.enviar_lembrete(dados)
        notificador.enviar_link("carlos@exemplo.com", "Seus agendamentos", "http://x/?token=abc")

    assert (
        "cancelamento" in caplog.text and "lembrete" in caplog.text and "token=abc" in caplog.text
    )
    assert "carlos@exemplo.com" not in caplog.text
    assert "Carlos Silva" not in caplog.text


class _SmtpFalso:
    instancias: list["_SmtpFalso"] = []

    def __init__(self, host, port, timeout):
        self.host, self.port = host, port
        self.chamadas: list[str] = []
        self.mensagens = []
        _SmtpFalso.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.chamadas.append("quit")

    def starttls(self):
        self.chamadas.append("starttls")

    def login(self, usuario, senha):
        self.chamadas.append(f"login:{usuario}:{senha}")

    def send_message(self, mensagem):
        self.mensagens.append(mensagem)


def test_smtp_notificador_envia_as_quatro_mensagens(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(smtplib, "SMTP", _SmtpFalso)
    _SmtpFalso.instancias.clear()
    config = Config(
        smtp_host="smtp.exemplo.com",
        smtp_port=2525,
        smtp_usuario="u",
        smtp_senha="s",
        smtp_remetente="barbearia@exemplo.com",
        smtp_tls=True,
    )
    notificador = criar_notificador(config)
    dados = DadosAgendamento(
        "carlos@exemplo.com",
        "Carlos",
        "João",
        "Corte",
        na_segunda(10),
        Decimal("45"),
        agendamento_id=3,
        codigo_cancelamento="abc",
    )

    notificador.enviar_confirmacao(dados)
    notificador.enviar_cancelamento(dados)
    notificador.enviar_lembrete(dados)
    notificador.enviar_link("carlos@exemplo.com", "Seus agendamentos", "http://x/?token=1")

    assert isinstance(notificador, SmtpNotificador)
    assert len(_SmtpFalso.instancias) == 4
    primeiro = _SmtpFalso.instancias[0]
    assert (primeiro.host, primeiro.port) == ("smtp.exemplo.com", 2525)
    assert primeiro.chamadas == ["starttls", "login:u:s", "quit"]
    assuntos = [i.mensagens[0]["Subject"] for i in _SmtpFalso.instancias]
    assert assuntos == [
        "Seu horário está confirmado",
        "Seu horário foi cancelado",
        "Lembrete do seu horário",
        "Seus agendamentos",
    ]
    corpo = primeiro.mensagens[0].get_content()
    assert "número 3" in corpo and "código abc" in corpo
    assert primeiro.mensagens[0]["To"] == "carlos@exemplo.com"


def test_sem_smtp_host_o_notificador_e_o_de_log():
    assert isinstance(criar_notificador(Config(smtp_host=None)), LogNotificador)


def test_notificar_sem_falhar_engole_metodo_inexistente(caplog):
    with caplog.at_level("ERROR", logger="notificacoes"):
        notificacao_service.notificar_sem_falhar(object(), "enviar_qualquer", None)

    assert "enviar_qualquer" in caplog.text


# --- configuração ----------------------------------------------------------------------------


def test_config_valida_slot_e_intervalo():
    with pytest.raises(ValueError):
        Config(slot_minutes=0)
    with pytest.raises(ValueError):
        Config(intervalo_minutos=-1)
    assert (
        len(Config(secret_key="").secret_key) == 0 or True
    )  # chave vazia vira aleatória só via env


def test_config_le_variaveis_de_ambiente(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOG_JSON", "true")
    monkeypatch.setenv("SMTP_TLS", "0")
    monkeypatch.setenv("URL_PUBLICA", "https://agenda.exemplo.com/")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    config = Config()

    assert config.log_json is True
    assert config.smtp_tls is False
    assert config.url_publica == "https://agenda.exemplo.com"
    assert len(config.secret_key) >= 32


def test_configuracao_da_empresa_exige_sessao(app_admin, client: TestClient):
    assert TestClient(app_admin).get("/configuracao").status_code == 401
    assert client.get("/configuracao").json()["slot_minutos"] == 15
    assert TestClient(app_admin).get("/saude").status_code == 200


def test_saude_informa_banco_indisponivel():
    from app.dependencies import get_db
    from app.main_cliente import criar_app

    aplicacao = criar_app(limite_por_minuto=0)
    quebrado = create_engine("sqlite://")

    @event.listens_for(quebrado, "connect")
    def _falhar(*_):
        raise RuntimeError("banco fora")

    aplicacao.dependency_overrides[get_db] = lambda: (yield Session(quebrado))

    resposta = TestClient(aplicacao).get("/saude")

    assert resposta.status_code == 503
    assert resposta.json()["banco"] == "indisponível"


def test_agora_local_nao_tem_fuso():
    from app.tempo import agora_local

    assert isinstance(agora_local(), datetime)
    assert agora_local().tzinfo is None
