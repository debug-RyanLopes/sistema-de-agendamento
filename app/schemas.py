import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models import CENTAVOS, StatusAgendamento


def _validar_email(valor: str) -> str:
    valor = valor.strip().lower()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", valor):
        raise ValueError(f"e-mail inválido: {valor}")
    return valor


Email = Annotated[str, AfterValidator(_validar_email)]


def _validar_telefone(valor: str) -> str:
    """Aceita telefone brasileiro com DDD, com ou sem máscara; guarda só os dígitos."""
    digitos = re.sub(r"[\s().+-]", "", valor)
    if not digitos.isdigit():
        raise ValueError("telefone deve ter só números, espaços, parênteses ou hífen")
    if digitos.startswith("0") or len(digitos) not in (10, 11):
        raise ValueError("informe o telefone com DDD, ex.: (92) 91234-5678")
    if len(digitos) == 11 and digitos[2] != "9":
        raise ValueError("celular com 11 dígitos deve ter 9 depois do DDD")
    if len(digitos) == 10 and digitos[2] not in "2345":
        raise ValueError("telefone fixo deve começar com 2, 3, 4 ou 5 depois do DDD")
    return digitos


Telefone = Annotated[str, AfterValidator(_validar_telefone)]


Dinheiro = Annotated[
    Decimal,
    Field(ge=0, max_digits=10, decimal_places=2),
    AfterValidator(lambda valor: valor.quantize(CENTAVOS)),
]


def _sem_fuso(valor: datetime) -> datetime:
    if valor.tzinfo is not None:
        raise ValueError("use o horário de Manaus, sem fuso")
    return valor


HorarioLocal = Annotated[datetime, AfterValidator(_sem_fuso)]


class ErroOut(BaseModel):
    detail: str


ERRO_404 = {404: {"model": ErroOut, "description": "Recurso não encontrado"}}
ERRO_409 = {409: {"model": ErroOut, "description": "Conflito de horário com outro agendamento"}}
ERRO_422 = {
    422: {"description": "Dados inválidos, recurso inativo, fora da disponibilidade ou no passado"}
}


class _Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AtivoIn(BaseModel):
    ativo: bool


class ClienteIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100, examples=["Carlos Silva"])
    email: Email = Field(examples=["carlos@exemplo.com"])
    telefone: Telefone = Field(examples=["(92) 91234-5678"])


class ClienteOut(_Saida):
    id: int
    nome: str
    email: str
    telefone: str
    ativo: bool


class BarbeiroIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100, examples=["João Barbeiro"])
    email: Email = Field(examples=["joao@barbearia.com"])


class BarbeiroOut(_Saida):
    id: int
    nome: str
    email: str
    ativo: bool


class ServicoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100, examples=["Corte de cabelo"])
    duracao_minutos: int = Field(gt=0, le=480, examples=[30])
    preco: Dinheiro = Field(examples=["45.00"])


class ServicoOut(_Saida):
    id: int
    nome: str
    duracao_minutos: int
    preco: Dinheiro
    ativo: bool


class ServicoPublicoOut(_Saida):
    id: int
    nome: str
    duracao_minutos: int
    preco: Dinheiro


class ProdutoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100, examples=["Pomada modeladora"])
    preco: Dinheiro = Field(examples=["35.90"])
    estoque: int = Field(ge=0, le=100000, examples=[12])


class ProdutoOut(_Saida):
    id: int
    nome: str
    preco: Dinheiro
    estoque: int
    ativo: bool


class DisponibilidadeIn(BaseModel):
    dia_semana: int = Field(ge=0, le=6, description="0 = segunda-feira ... 6 = domingo")
    hora_inicio: time = Field(examples=["09:00:00"])
    hora_fim: time = Field(examples=["18:00:00"])

    @model_validator(mode="after")
    def _inicio_antes_do_fim(self) -> "DisponibilidadeIn":
        if self.hora_inicio >= self.hora_fim:
            raise ValueError("hora_inicio deve ser anterior a hora_fim")
        return self


class DisponibilidadeOut(_Saida):
    id: int
    barbeiro_id: int
    dia_semana: int
    hora_inicio: time
    hora_fim: time


class AgendamentoIn(BaseModel):
    cliente_id: int
    barbeiro_id: int
    servico_id: int
    inicio: HorarioLocal = Field(
        description="Horário de Manaus (UTC-4), sem fuso", examples=["2030-01-07T10:00:00"]
    )


class AgendamentoOut(_Saida):
    id: int
    cliente_id: int
    barbeiro_id: int
    servico_id: int
    inicio: datetime
    fim: datetime
    status: StatusAgendamento


class PaginaAgendamentosOut(BaseModel):
    itens: list[AgendamentoOut]
    total: int
    limite: int
    deslocamento: int


class HorariosLivresOut(BaseModel):
    barbeiro_id: int
    servico_id: int
    data: date
    horarios: list[datetime]


class AgendamentoPublicoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100, examples=["Carlos Silva"])
    email: Email = Field(examples=["carlos@exemplo.com"])
    telefone: Telefone = Field(examples=["(92) 91234-5678"])
    barbeiro_id: int
    servico_id: int
    inicio: HorarioLocal = Field(
        description="Horário de Manaus (UTC-4), sem fuso", examples=["2030-01-07T10:00:00"]
    )


class ConfirmacaoOut(BaseModel):
    id: int
    codigo_cancelamento: str
    barbeiro: str
    servico: str
    inicio: datetime
    fim: datetime
    preco: Dinheiro
    status: StatusAgendamento


class CancelamentoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=64)


class CancelamentoOut(BaseModel):
    id: int
    status: StatusAgendamento


class BarbeiroDisponivelOut(BaseModel):
    id: int
    nome: str
    horarios: list[datetime]


class DisponibilidadeDiaOut(BaseModel):
    data: date
    servico_id: int
    barbeiros: list[BarbeiroDisponivelOut]


class AgendamentoFuturoOut(BaseModel):
    id: int
    inicio: datetime
    cliente: str
    servico: str
    preco: Dinheiro


class ImpactoDesativacaoOut(BaseModel):
    barbeiro_id: int
    nome: str
    ativo: bool
    cadastrado_em: datetime | None
    dias_na_empresa: int | None
    atendimentos_realizados: int
    total_futuros: int
    valor_futuro: Dinheiro
    proximo_atendimento: datetime | None
    agendamentos_futuros: list[AgendamentoFuturoOut]
