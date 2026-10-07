import re
from datetime import date, datetime, time
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models import StatusAgendamento


def _validar_email(valor: str) -> str:
    valor = valor.strip().lower()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", valor):
        raise ValueError(f"e-mail inválido: {valor}")
    return valor


Email = Annotated[str, AfterValidator(_validar_email)]


class ErroOut(BaseModel):
    detail: str


ERRO_404 = {404: {"model": ErroOut, "description": "Recurso não encontrado"}}
ERRO_409 = {409: {"model": ErroOut, "description": "Conflito de horário com outro agendamento"}}
ERRO_422 = {422: {"description": "Dados inválidos, fora da disponibilidade ou no passado"}}


class _Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClienteIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100, examples=["Carlos Silva"])
    email: Email = Field(examples=["carlos@exemplo.com"])
    telefone: str = Field(min_length=8, max_length=20, examples=["11987654321"])


class ClienteOut(_Saida):
    id: int
    nome: str
    email: str
    telefone: str


class BarbeiroIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100, examples=["João Barbeiro"])
    email: Email = Field(examples=["joao@barbearia.com"])


class BarbeiroOut(_Saida):
    id: int
    nome: str
    email: str


class ServicoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100, examples=["Corte de cabelo"])
    duracao_minutos: int = Field(gt=0, le=480, examples=[30])
    preco: float = Field(ge=0, examples=[45.0])


class ServicoOut(_Saida):
    id: int
    nome: str
    duracao_minutos: int
    preco: float


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
    inicio: datetime = Field(
        description="Horário local, sem fuso", examples=["2030-01-07T10:00:00"]
    )

    @field_validator("inicio")
    @classmethod
    def _sem_fuso(cls, valor: datetime) -> datetime:
        if valor.tzinfo is not None:
            raise ValueError("use horário local, sem fuso")
        return valor


class AgendamentoOut(_Saida):
    id: int
    cliente_id: int
    barbeiro_id: int
    servico_id: int
    inicio: datetime
    fim: datetime
    status: StatusAgendamento


class HorariosLivresOut(BaseModel):
    barbeiro_id: int
    servico_id: int
    data: date
    horarios: list[datetime]
