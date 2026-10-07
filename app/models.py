import enum
from datetime import datetime, time

from sqlalchemy import Enum, Float, ForeignKey, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StatusAgendamento(str, enum.Enum):
    AGENDADO = "agendado"
    CANCELADO = "cancelado"


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    telefone: Mapped[str] = mapped_column(String(20))


class Barbeiro(Base):
    __tablename__ = "barbeiros"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))


class Servico(Base):
    __tablename__ = "servicos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    duracao_minutos: Mapped[int]
    preco: Mapped[float] = mapped_column(Float)


class Disponibilidade(Base):
    __tablename__ = "disponibilidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    barbeiro_id: Mapped[int] = mapped_column(ForeignKey("barbeiros.id"), index=True)
    dia_semana: Mapped[int]
    hora_inicio: Mapped[time]
    hora_fim: Mapped[time]


class Agendamento(Base):
    __tablename__ = "agendamentos"
    __table_args__ = (Index("ix_agendamentos_barbeiro_inicio", "barbeiro_id", "inicio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    barbeiro_id: Mapped[int] = mapped_column(ForeignKey("barbeiros.id"))
    servico_id: Mapped[int] = mapped_column(ForeignKey("servicos.id"))
    inicio: Mapped[datetime]
    fim: Mapped[datetime]
    status: Mapped[StatusAgendamento] = mapped_column(
        Enum(StatusAgendamento), default=StatusAgendamento.AGENDADO
    )
