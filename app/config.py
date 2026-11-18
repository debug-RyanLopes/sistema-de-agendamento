import os
import secrets
from dataclasses import dataclass, field

USUARIO_ADMIN = "admin"


def _int(nome: str, padrao: str) -> int:
    return int(os.getenv(nome, padrao))


def _bool(nome: str, padrao: str) -> bool:
    return os.getenv(nome, padrao).strip().lower() in ("1", "true", "sim", "yes")


@dataclass(frozen=True, slots=True)
class Config:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./barbearia.db")
    )
    slot_minutes: int = field(default_factory=lambda: _int("SLOT_MINUTES", "15"))
    intervalo_minutos: int = field(default_factory=lambda: _int("INTERVALO_MINUTOS", "0"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    log_json: bool = field(default_factory=lambda: _bool("LOG_JSON", "0"))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "America/Manaus"))
    admin_password: str | None = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD") or None)
    secret_key: str = field(
        default_factory=lambda: os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
    )
    max_agendamentos_ativos_por_cliente: int = field(
        default_factory=lambda: _int("MAX_AGENDAMENTOS_ATIVOS_POR_CLIENTE", "3")
    )
    limite_requisicoes_por_minuto: int = field(
        default_factory=lambda: _int("LIMITE_REQUISICOES_POR_MINUTO", "60")
    )
    smtp_host: str | None = field(default_factory=lambda: os.getenv("SMTP_HOST") or None)
    smtp_port: int = field(default_factory=lambda: _int("SMTP_PORT", "587"))
    smtp_usuario: str | None = field(default_factory=lambda: os.getenv("SMTP_USUARIO") or None)
    smtp_senha: str | None = field(default_factory=lambda: os.getenv("SMTP_SENHA") or None)
    smtp_remetente: str = field(
        default_factory=lambda: os.getenv("SMTP_REMETENTE", "barbearia@exemplo.com")
    )
    smtp_tls: bool = field(default_factory=lambda: _bool("SMTP_TLS", "1"))
    lembrete_horas: int = field(default_factory=lambda: _int("LEMBRETE_HORAS", "24"))
    url_publica: str = field(
        default_factory=lambda: os.getenv("URL_PUBLICA", "http://127.0.0.1:8000").rstrip("/")
    )

    def __post_init__(self) -> None:
        if self.slot_minutes < 1:
            raise ValueError("slot_minutes must be >= 1")
        if self.intervalo_minutos < 0:
            raise ValueError("intervalo_minutos must be >= 0")


CONFIG = Config()
