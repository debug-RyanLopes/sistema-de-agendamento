import logging
import warnings

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import IntegrityError, SAWarning
from sqlalchemy.orm import Session, sessionmaker

from app.config import CONFIG

log = logging.getLogger(__name__)

OPCAO_TRANSACAO = "transacao"
ESCRITA = {OPCAO_TRANSACAO: "IMMEDIATE"}


def _e_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def criar_motor(url: str) -> Engine:
    if not _e_sqlite(url):
        return create_engine(url, pool_pre_ping=True)

    motor = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _preparar_conexao(dbapi_connection, _registro) -> None:
        # O driver não abre transação sozinho: quem decide é o evento "begin" abaixo.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        # WAL deixa leitores e escritor conviverem; em banco em memória é ignorado.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    @event.listens_for(motor, "begin")
    def _iniciar_transacao(conexao) -> None:
        # Leituras usam BEGIN DEFERRED (não bloqueiam ninguém). Quem vai gravar pede
        # IMMEDIATE via `iniciar_escrita`, e aí a checagem de conflito e o INSERT
        # acontecem sob o mesmo bloqueio de escrita.
        modo = conexao.get_execution_options().get(OPCAO_TRANSACAO, "DEFERRED")
        conexao.exec_driver_sql(f"BEGIN {modo}")

    return motor


def iniciar_escrita(session: Session) -> None:
    """Abre a transação da sessão já em modo de escrita.

    Deve ser chamada antes da primeira consulta da transação (cada requisição tem uma
    sessão nova, então nos serviços isso é natural). Se a sessão já tem uma transação
    de leitura aberta, não faz nada: a escrita ainda acontece, só sem a reserva
    antecipada do bloqueio. No SQLite vira `BEGIN IMMEDIATE`; em outros bancos o
    bloqueio de linha fica a cargo de `SELECT ... FOR UPDATE` nos repositórios.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SAWarning)
        session.connection(execution_options=ESCRITA)


engine = criar_motor(CONFIG.database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

COLUNAS_ADICIONADAS = {
    "clientes": [
        ("ativo", "BOOLEAN NOT NULL DEFAULT 1"),
        ("anonimizado_em", "DATETIME"),
    ],
    "barbeiros": [("ativo", "BOOLEAN NOT NULL DEFAULT 1"), ("criado_em", "DATETIME")],
    "servicos": [("ativo", "BOOLEAN NOT NULL DEFAULT 1")],
    "agendamentos": [
        ("codigo_cancelamento", "VARCHAR(64)"),
        ("criado_em", "DATETIME"),
        ("origem", "VARCHAR(10)"),
        ("cancelado_em", "DATETIME"),
        ("cancelado_por", "VARCHAR(10)"),
        ("motivo_cancelamento", "VARCHAR(200)"),
        ("lembrete_enviado_em", "DATETIME"),
    ],
}

INDICES_UNICOS = {
    "clientes": "uq_clientes_email",
    "barbeiros": "uq_barbeiros_email",
}


def _conexao_de_escrita(motor: Engine):
    conexao = motor.connect()
    if _e_sqlite(str(motor.url)):
        conexao = conexao.execution_options(**ESCRITA)
    return conexao


def aplicar_migracoes(motor: Engine) -> None:
    """Acrescenta colunas e índices a bancos antigos sem apagar dados. Idempotente."""
    if not _e_sqlite(str(motor.url)):
        # Em outros bancos o esquema é criado completo pelo create_all; colunas novas
        # em bancos já existentes ficam a cargo de uma migração própria.
        return
    with _conexao_de_escrita(motor) as conexao, conexao.begin():
        for tabela, colunas in COLUNAS_ADICIONADAS.items():
            existentes = {
                linha[1] for linha in conexao.exec_driver_sql(f"PRAGMA table_info({tabela})")
            }
            for nome, definicao in colunas:
                if nome not in existentes:
                    conexao.exec_driver_sql(f"ALTER TABLE {tabela} ADD COLUMN {nome} {definicao}")

    with _conexao_de_escrita(motor) as conexao, conexao.begin():
        conexao.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agendamentos_inicio ON agendamentos (inicio)"
        )
    for tabela, indice in INDICES_UNICOS.items():
        _garantir_email_unico(motor, tabela, indice)


def _garantir_email_unico(motor: Engine, tabela: str, indice: str) -> None:
    try:
        with _conexao_de_escrita(motor) as conexao, conexao.begin():
            conexao.exec_driver_sql(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {indice} ON {tabela} (email)"
            )
    except IntegrityError:
        log.warning(
            "Há %s com e-mail repetido; o índice único não foi criado. "
            "Unifique os cadastros repetidos e reinicie.",
            tabela,
        )
