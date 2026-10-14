from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import aplicar_migracoes, criar_motor
from app.models import Agendamento, Barbeiro, Base, Cliente, Servico

ESQUEMA_ANTIGO = [
    "CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL,"
    " email VARCHAR(254) NOT NULL, telefone VARCHAR(20) NOT NULL)",
    "CREATE TABLE barbeiros (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL,"
    " email VARCHAR(254) NOT NULL)",
    "CREATE TABLE servicos (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL,"
    " duracao_minutos INTEGER NOT NULL, preco FLOAT NOT NULL)",
    "CREATE TABLE disponibilidades (id INTEGER PRIMARY KEY, barbeiro_id INTEGER NOT NULL,"
    " dia_semana INTEGER NOT NULL, hora_inicio TIME NOT NULL, hora_fim TIME NOT NULL)",
    "CREATE TABLE agendamentos (id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL,"
    " barbeiro_id INTEGER NOT NULL, servico_id INTEGER NOT NULL, inicio DATETIME NOT NULL,"
    " fim DATETIME NOT NULL, status VARCHAR(9) NOT NULL)",
    "INSERT INTO clientes VALUES (1, 'Carlos Silva', 'carlos@exemplo.com', '11987654321')",
    "INSERT INTO barbeiros VALUES (1, 'João Barbeiro', 'joao@barbearia.com')",
    "INSERT INTO servicos VALUES (1, 'Corte', 30, 45.0)",
    "INSERT INTO agendamentos VALUES (1, 1, 1, 1, '2030-01-07 10:00:00.000000',"
    " '2030-01-07 10:30:00.000000', 'AGENDADO')",
]


def _criar_banco_antigo(caminho: Path) -> str:
    url = f"sqlite:///{caminho.as_posix()}"
    motor = create_engine(url)
    with motor.begin() as conexao:
        for comando in ESQUEMA_ANTIGO:
            conexao.exec_driver_sql(comando)
    motor.dispose()
    return url


def _migrar(url: str) -> None:
    motor = criar_motor(url)
    Base.metadata.create_all(motor)
    aplicar_migracoes(motor)
    motor.dispose()


def test_migracao_adiciona_colunas_e_preserva_os_dados(tmp_path: Path):
    url = _criar_banco_antigo(tmp_path / "antigo.db")

    _migrar(url)

    motor = criar_motor(url)
    with Session(motor) as sessao:
        cliente = sessao.get(Cliente, 1)
        assert cliente.nome == "Carlos Silva"
        assert cliente.ativo is True
        assert sessao.get(Barbeiro, 1).ativo is True
        assert sessao.get(Servico, 1).ativo is True
        agendamento = sessao.get(Agendamento, 1)
        assert agendamento.inicio == datetime(2030, 1, 7, 10, 0)
        assert agendamento.codigo_cancelamento is None
    motor.dispose()


def test_migracao_pode_rodar_varias_vezes(tmp_path: Path):
    url = _criar_banco_antigo(tmp_path / "antigo.db")

    _migrar(url)
    _migrar(url)

    motor = criar_motor(url)
    with Session(motor) as sessao:
        assert sessao.get(Cliente, 1).ativo is True
    motor.dispose()


def test_migracao_em_banco_novo_nao_altera_nada(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'novo.db').as_posix()}"

    _migrar(url)

    motor = criar_motor(url)
    with motor.connect() as conexao:
        colunas = {linha[1] for linha in conexao.exec_driver_sql("PRAGMA table_info(clientes)")}
    assert {"ativo", "nome", "email", "telefone"} <= colunas
    motor.dispose()


def test_novos_registros_do_banco_migrado_nascem_ativos(tmp_path: Path):
    url = _criar_banco_antigo(tmp_path / "antigo.db")
    _migrar(url)

    motor = criar_motor(url)
    with Session(motor) as sessao:
        novo = Cliente(nome="Ana Souza", email="ana@exemplo.com", telefone="11999998888")
        sessao.add(novo)
        sessao.commit()
        assert sessao.get(Cliente, novo.id).ativo is True
    motor.dispose()
