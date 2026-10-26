import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from email.message import EmailMessage
from typing import Protocol

from app.config import CONFIG, Config

log = logging.getLogger("notificacoes")


@dataclass(frozen=True, slots=True)
class DadosAgendamento:
    email: str
    cliente: str
    barbeiro: str
    servico: str
    inicio: datetime
    preco: Decimal
    agendamento_id: int | None = None
    codigo_cancelamento: str | None = None


# Nome antigo, mantido para quem importava a confirmação.
DadosConfirmacao = DadosAgendamento


class Notificador(Protocol):
    def enviar_confirmacao(self, dados: DadosAgendamento) -> None: ...

    def enviar_cancelamento(self, dados: DadosAgendamento) -> None: ...

    def enviar_lembrete(self, dados: DadosAgendamento) -> None: ...

    def enviar_link(self, email: str, assunto: str, url: str) -> None: ...


def mascarar_email(email: str) -> str:
    """`carlos@exemplo.com` vira `c***s@exemplo.com`: dá para depurar sem expor o dado."""
    usuario, _, dominio = email.partition("@")
    if len(usuario) <= 2:
        return f"{usuario[:1]}***@{dominio}"
    return f"{usuario[0]}***{usuario[-1]}@{dominio}"


def _quando(dados: DadosAgendamento) -> str:
    return dados.inicio.strftime("%d/%m/%Y %H:%M")


def texto_confirmacao(dados: DadosAgendamento) -> tuple[str, str]:
    codigo = (
        f"\nPara cancelar ou reagendar use o número {dados.agendamento_id} "
        f"e o código {dados.codigo_cancelamento}."
        if dados.codigo_cancelamento
        else ""
    )
    return (
        "Seu horário está confirmado",
        f"Olá, {dados.cliente}!\n\nSeu horário com {dados.barbeiro} para {dados.servico} "
        f"está confirmado em {_quando(dados)} (R$ {dados.preco:.2f}).{codigo}\n",
    )


def texto_cancelamento(dados: DadosAgendamento) -> tuple[str, str]:
    return (
        "Seu horário foi cancelado",
        f"Olá, {dados.cliente}.\n\nO horário com {dados.barbeiro} para {dados.servico} "
        f"em {_quando(dados)} foi cancelado. Se não foi você, marque um novo horário.\n",
    )


def texto_lembrete(dados: DadosAgendamento) -> tuple[str, str]:
    return (
        "Lembrete do seu horário",
        f"Olá, {dados.cliente}!\n\nLembrando: {dados.servico} com {dados.barbeiro} "
        f"em {_quando(dados)}. Até lá!\n",
    )


class LogNotificador:
    """Escreve no log em vez de enviar. Nunca registra nome nem e-mail completo."""

    def _registrar(self, tipo: str, dados: DadosAgendamento) -> None:
        log.info(
            "E-mail de %s para %s: %s com %s em %s (R$ %.2f)",
            tipo,
            mascarar_email(dados.email),
            dados.servico,
            dados.barbeiro,
            _quando(dados),
            dados.preco,
        )

    def enviar_confirmacao(self, dados: DadosAgendamento) -> None:
        self._registrar("confirmação", dados)

    def enviar_cancelamento(self, dados: DadosAgendamento) -> None:
        self._registrar("cancelamento", dados)

    def enviar_lembrete(self, dados: DadosAgendamento) -> None:
        self._registrar("lembrete", dados)

    def enviar_link(self, email: str, assunto: str, url: str) -> None:
        # Em desenvolvimento o link precisa aparecer em algum lugar: fica no log.
        log.info("E-mail '%s' para %s: %s", assunto, mascarar_email(email), url)


class SmtpNotificador:
    def __init__(self, config: Config) -> None:
        self.config = config

    def _enviar(self, destinatario: str, assunto: str, corpo: str) -> None:
        mensagem = EmailMessage()
        mensagem["From"] = self.config.smtp_remetente
        mensagem["To"] = destinatario
        mensagem["Subject"] = assunto
        mensagem.set_content(corpo)
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=15) as smtp:
            if self.config.smtp_tls:
                smtp.starttls()
            if self.config.smtp_usuario:
                smtp.login(self.config.smtp_usuario, self.config.smtp_senha or "")
            smtp.send_message(mensagem)
        log.info("E-mail '%s' enviado para %s", assunto, mascarar_email(destinatario))

    def enviar_confirmacao(self, dados: DadosAgendamento) -> None:
        self._enviar(dados.email, *texto_confirmacao(dados))

    def enviar_cancelamento(self, dados: DadosAgendamento) -> None:
        self._enviar(dados.email, *texto_cancelamento(dados))

    def enviar_lembrete(self, dados: DadosAgendamento) -> None:
        self._enviar(dados.email, *texto_lembrete(dados))

    def enviar_link(self, email: str, assunto: str, url: str) -> None:
        self._enviar(email, assunto, f"Abra este link para continuar:\n\n{url}\n")


def criar_notificador(config: Config = CONFIG) -> Notificador:
    return SmtpNotificador(config) if config.smtp_host else LogNotificador()


def enviar_sem_falhar(notificador: Notificador, dados: DadosAgendamento) -> None:
    notificar_sem_falhar(notificador, "enviar_confirmacao", dados)


def notificar_sem_falhar(notificador: Notificador, metodo: str, *argumentos) -> None:
    """Notificação é melhor esforço: a resposta já foi dada; falha vira log."""
    try:
        getattr(notificador, metodo)(*argumentos)
    except Exception:
        log.exception("falha ao enviar notificação (%s)", metodo)
