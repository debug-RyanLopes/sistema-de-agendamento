import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

log = logging.getLogger("notificacoes")


@dataclass(frozen=True, slots=True)
class DadosConfirmacao:
    email: str
    cliente: str
    barbeiro: str
    servico: str
    inicio: datetime
    preco: float


class Notificador(Protocol):
    def enviar_confirmacao(self, dados: DadosConfirmacao) -> None: ...


class LogNotificador:
    def enviar_confirmacao(self, dados: DadosConfirmacao) -> None:
        log.info(
            "E-mail para %s: Olá, %s! Seu horário com %s para %s está confirmado em %s (R$ %.2f).",
            dados.email,
            dados.cliente,
            dados.barbeiro,
            dados.servico,
            dados.inicio.strftime("%d/%m/%Y %H:%M"),
            dados.preco,
        )


def enviar_sem_falhar(notificador: Notificador, dados: DadosConfirmacao) -> None:
    try:
        notificador.enviar_confirmacao(dados)
    except Exception:
        log.exception("falha ao enviar confirmação")
