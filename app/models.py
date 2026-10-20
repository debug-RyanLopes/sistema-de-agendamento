import enum
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import Enum, Float, ForeignKey, Index, String, TypeDecorator, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.tempo import agora_local

CENTAVOS = Decimal("0.01")


class Base(DeclarativeBase):
    pass


class Dinheiro(TypeDecorator):
    """Valor monetário: sempre `Decimal` com 2 casas no Python.

    O SQLite não tem tipo decimal; o valor é guardado como REAL e reconvertido via `str`,
    o que é exato para 2 casas. Nenhuma conta é feita em `float`.
    """

    impl = Float
    cache_ok = True

    def process_bind_param(self, valor: Decimal | None, dialect) -> float | None:
        return None if valor is None else float(Decimal(valor).quantize(CENTAVOS))

    def process_result_value(self, valor: float | None, dialect) -> Decimal | None:
        return None if valor is None else Decimal(str(valor)).quantize(CENTAVOS)


class StatusAgendamento(str, enum.Enum):
    AGENDADO = "agendado"
    CANCELADO = "cancelado"


def _coluna_ativo() -> Mapped[bool]:
    return mapped_column(default=True, server_default=true())


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (Index("uq_clientes_email", "email", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    telefone: Mapped[str] = mapped_column(String(20))
    ativo: Mapped[bool] = _coluna_ativo()


class Barbeiro(Base):
    __tablename__ = "barbeiros"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    ativo: Mapped[bool] = _coluna_ativo()
    criado_em: Mapped[datetime | None] = mapped_column(default=agora_local)


class Servico(Base):
    __tablename__ = "servicos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    duracao_minutos: Mapped[int]
    preco: Mapped[Decimal] = mapped_column(Dinheiro)
    ativo: Mapped[bool] = _coluna_ativo()


class Produto(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    preco: Mapped[Decimal] = mapped_column(Dinheiro)
    estoque: Mapped[int] = mapped_column(default=0)
    ativo: Mapped[bool] = _coluna_ativo()


class Disponibilidade(Base):
    __tablename__ = "disponibilidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    barbeiro_id: Mapped[int] = mapped_column(ForeignKey("barbeiros.id"), index=True)
    dia_semana: Mapped[int]
    hora_inicio: Mapped[time]
    hora_fim: Mapped[time]


class Agendamento(Base):
    __tablename__ = "agendamentos"
    __table_args__ = (
        Index("ix_agendamentos_barbeiro_inicio", "barbeiro_id", "inicio"),
        Index("ix_agendamentos_inicio", "inicio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    barbeiro_id: Mapped[int] = mapped_column(ForeignKey("barbeiros.id"))
    servico_id: Mapped[int] = mapped_column(ForeignKey("servicos.id"))
    inicio: Mapped[datetime]
    fim: Mapped[datetime]
    status: Mapped[StatusAgendamento] = mapped_column(
        Enum(StatusAgendamento), default=StatusAgendamento.AGENDADO
    )
    codigo_cancelamento: Mapped[str | None] = mapped_column(String(64), default=None)
