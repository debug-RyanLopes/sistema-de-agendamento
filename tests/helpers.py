from datetime import datetime

from app.services.notificacao_service import DadosConfirmacao

AGORA_FIXO = datetime(2030, 1, 1, 8, 0)
SEGUNDA = datetime(2030, 1, 7)
DOMINGO = datetime(2030, 1, 6)


def na_segunda(hora: int, minuto: int = 0) -> datetime:
    return SEGUNDA.replace(hour=hora, minute=minuto)


class NotificadorFalso:
    def __init__(self) -> None:
        self.enviados: list[DadosConfirmacao] = []

    def enviar_confirmacao(self, dados: DadosConfirmacao) -> None:
        self.enviados.append(dados)


class NotificadorQuebrado:
    def enviar_confirmacao(self, dados: DadosConfirmacao) -> None:
        raise RuntimeError("servidor de e-mail indisponível")
