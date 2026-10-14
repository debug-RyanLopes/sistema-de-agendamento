import os
from dataclasses import dataclass, field

USUARIO_ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class Config:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./barbearia.db")
    )
    slot_minutes: int = field(default_factory=lambda: int(os.getenv("SLOT_MINUTES", "15")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    admin_password: str | None = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD") or None)

    def __post_init__(self) -> None:
        if self.slot_minutes < 1:
            raise ValueError("slot_minutes must be >= 1")


CONFIG = Config()
