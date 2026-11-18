from datetime import datetime

from app.services.notificacao_service import DadosAgendamento

AGORA_FIXO = datetime(2030, 1, 1, 8, 0)
SEGUNDA = datetime(2030, 1, 7)
DOMINGO = datetime(2030, 1, 6)


def na_segunda(hora: int, minuto: int = 0) -> datetime:
    return SEGUNDA.replace(hour=hora, minute=minuto)


class NotificadorFalso:
    def __init__(self) -> None:
        self.enviados: list[DadosAgendamento] = []
        self.cancelamentos: list[DadosAgendamento] = []
        self.lembretes: list[DadosAgendamento] = []
        self.links: list[tuple[str, str, str]] = []

    def enviar_confirmacao(self, dados: DadosAgendamento) -> None:
        self.enviados.append(dados)

    def enviar_cancelamento(self, dados: DadosAgendamento) -> None:
        self.cancelamentos.append(dados)

    def enviar_lembrete(self, dados: DadosAgendamento) -> None:
        self.lembretes.append(dados)

    def enviar_link(self, email: str, assunto: str, url: str) -> None:
        self.links.append((email, assunto, url))


class NotificadorQuebrado:
    def enviar_confirmacao(self, dados: DadosAgendamento) -> None:
        raise RuntimeError("servidor de e-mail indisponível")

    def enviar_cancelamento(self, dados: DadosAgendamento) -> None:
        raise RuntimeError("servidor de e-mail indisponível")

    def enviar_lembrete(self, dados: DadosAgendamento) -> None:
        raise RuntimeError("servidor de e-mail indisponível")

    def enviar_link(self, email: str, assunto: str, url: str) -> None:
        raise RuntimeError("servidor de e-mail indisponível")
