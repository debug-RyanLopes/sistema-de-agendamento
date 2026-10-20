import logging

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import CONFIG

log = logging.getLogger(__name__)


def criar_motor(url: str) -> Engine:
    motor = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _desativar_begin_automatico(dbapi_connection, _registro) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(motor, "begin")
    def _iniciar_transacao_imediata(conexao) -> None:
        conexao.exec_driver_sql("BEGIN IMMEDIATE")

    return motor


engine = criar_motor(CONFIG.database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

COLUNAS_ADICIONADAS = {
    "clientes": [("ativo", "BOOLEAN NOT NULL DEFAULT 1")],
    "barbeiros": [("ativo", "BOOLEAN NOT NULL DEFAULT 1"), ("criado_em", "DATETIME")],
    "servicos": [("ativo", "BOOLEAN NOT NULL DEFAULT 1")],
    "agendamentos": [("codigo_cancelamento", "VARCHAR(64)")],
}


def aplicar_migracoes(motor: Engine) -> None:
    with motor.begin() as conexao:
        for tabela, colunas in COLUNAS_ADICIONADAS.items():
            existentes = {
                linha[1] for linha in conexao.exec_driver_sql(f"PRAGMA table_info({tabela})")
            }
            for nome, definicao in colunas:
                if nome not in existentes:
                    conexao.exec_driver_sql(f"ALTER TABLE {tabela} ADD COLUMN {nome} {definicao}")

    with motor.begin() as conexao:
        conexao.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agendamentos_inicio ON agendamentos (inicio)"
        )
    _garantir_email_unico(motor)


def _garantir_email_unico(motor: Engine) -> None:
    try:
        with motor.begin() as conexao:
            conexao.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_clientes_email ON clientes (email)"
            )
    except IntegrityError:
        log.warning(
            "Há clientes com e-mail repetido; o índice único não foi criado. "
            "Unifique os cadastros repetidos e reinicie."
        )
