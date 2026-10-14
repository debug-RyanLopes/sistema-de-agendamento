from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import CONFIG


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
    "barbeiros": [("ativo", "BOOLEAN NOT NULL DEFAULT 1")],
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
