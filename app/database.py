from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import CONFIG

engine = create_engine(CONFIG.database_url, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _desativar_begin_automatico(dbapi_connection, _registro) -> None:
    dbapi_connection.isolation_level = None


@event.listens_for(engine, "begin")
def _iniciar_transacao_imediata(conexao) -> None:
    conexao.exec_driver_sql("BEGIN IMMEDIATE")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
