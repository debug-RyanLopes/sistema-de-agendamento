import enum
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Enum, Float, ForeignKey, Index, Numeric, String, TypeDecorator, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.tempo import agora_local

CENTAVOS = Decimal("0.01")
TAMANHO_NOME = 120


class Base(DeclarativeBase):
    pass


class Dinheiro(TypeDecorator):
    """Valor monetário: sempre `Decimal` com 2 casas no Python.

    No SQLite (que não tem tipo decimal) é guardado como REAL e reconvertido via `str`,
    o que é exato para 2 casas. Em outros bancos usa NUMERIC(10, 2). Nenhuma conta é
    feita em `float`.
    """

    impl = Float
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Float())
        return dialect.type_descriptor(Numeric(10, 2))

    def process_bind_param(self, valor: Decimal | None, dialect) -> float | Decimal | None:
        if valor is None:
            return None
        quantizado = Decimal(valor).quantize(CENTAVOS)
        return float(quantizado) if dialect.name == "sqlite" else quantizado

    def process_result_value(self, valor, dialect) -> Decimal | None:
        return None if valor is None else Decimal(str(valor)).quantize(CENTAVOS)


class StatusAgendamento(str, enum.Enum):
    AGENDADO = "agendado"
    CANCELADO = "cancelado"
    CONCLUIDO = "concluido"
    NAO_COMPARECEU = "nao_compareceu"


STATUS_FINAIS_DO_PASSADO = (StatusAgendamento.CONCLUIDO, StatusAgendamento.NAO_COMPARECEU)


class Origem(str, enum.Enum):
    CLIENTE = "cliente"
    EMPRESA = "empresa"


class PapelUsuario(str, enum.Enum):
    DONO = "dono"
    BARBEIRO = "barbeiro"


def _coluna_ativo() -> Mapped[bool]:
    return mapped_column(default=True, server_default=true())


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (Index("uq_clientes_email", "email", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(TAMANHO_NOME))
    email: Mapped[str] = mapped_column(String(254))
    telefone: Mapped[str] = mapped_column(String(20))
    ativo: Mapped[bool] = _coluna_ativo()
    anonimizado_em: Mapped[datetime | None] = mapped_column(default=None)


class Barbeiro(Base):
    __tablename__ = "barbeiros"
    __table_args__ = (Index("uq_barbeiros_email", "email", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(TAMANHO_NOME))
    email: Mapped[str] = mapped_column(String(254))
    ativo: Mapped[bool] = _coluna_ativo()
    criado_em: Mapped[datetime | None] = mapped_column(default=agora_local)


class Servico(Base):
    __tablename__ = "servicos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(TAMANHO_NOME))
    duracao_minutos: Mapped[int]
    preco: Mapped[Decimal] = mapped_column(Dinheiro)
    ativo: Mapped[bool] = _coluna_ativo()


class Produto(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(TAMANHO_NOME))
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


class Bloqueio(Base):
    """Folga, feriado ou bloqueio pontual. Sem barbeiro vale para a barbearia toda;
    sem horas vale o dia inteiro."""

    __tablename__ = "bloqueios"
    __table_args__ = (Index("ix_bloqueios_data", "data"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    barbeiro_id: Mapped[int | None] = mapped_column(ForeignKey("barbeiros.id"), default=None)
    data: Mapped[date]
    hora_inicio: Mapped[time | None] = mapped_column(default=None)
    hora_fim: Mapped[time | None] = mapped_column(default=None)
    motivo: Mapped[str | None] = mapped_column(String(100), default=None)


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
    criado_em: Mapped[datetime | None] = mapped_column(default=agora_local)
    origem: Mapped[Origem | None] = mapped_column(Enum(Origem), default=None)
    cancelado_em: Mapped[datetime | None] = mapped_column(default=None)
    cancelado_por: Mapped[Origem | None] = mapped_column(Enum(Origem), default=None)
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(200), default=None)
    lembrete_enviado_em: Mapped[datetime | None] = mapped_column(default=None)
    # Soma dos serviços no momento da marcação (serviço antigo sem este campo usa o preço atual).
    preco: Mapped[Decimal | None] = mapped_column(Dinheiro, default=None)


class AgendamentoServico(Base):
    """Serviços de um agendamento (um ou mais, ex.: Corte + Barba), com o preço da época."""

    __tablename__ = "agendamento_servicos"

    id: Mapped[int] = mapped_column(primary_key=True)
    agendamento_id: Mapped[int] = mapped_column(ForeignKey("agendamentos.id"), index=True)
    servico_id: Mapped[int] = mapped_column(ForeignKey("servicos.id"))
    ordem: Mapped[int] = mapped_column(default=0)
    preco: Mapped[Decimal] = mapped_column(Dinheiro)
    duracao_minutos: Mapped[int]


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (Index("uq_usuarios_login", "login", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(TAMANHO_NOME))
    login: Mapped[str] = mapped_column(String(100))
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[PapelUsuario] = mapped_column(Enum(PapelUsuario), default=PapelUsuario.DONO)
    barbeiro_id: Mapped[int | None] = mapped_column(ForeignKey("barbeiros.id"), default=None)
    ativo: Mapped[bool] = _coluna_ativo()
    criado_em: Mapped[datetime | None] = mapped_column(default=agora_local)


class Venda(Base):
    __tablename__ = "vendas"

    id: Mapped[int] = mapped_column(primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(default=agora_local)
    total: Mapped[Decimal] = mapped_column(Dinheiro)
    observacao: Mapped[str | None] = mapped_column(String(200), default=None)


class VendaItem(Base):
    __tablename__ = "venda_itens"

    id: Mapped[int] = mapped_column(primary_key=True)
    venda_id: Mapped[int] = mapped_column(ForeignKey("vendas.id"), index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"))
    quantidade: Mapped[int]
    preco_unitario: Mapped[Decimal] = mapped_column(Dinheiro)
