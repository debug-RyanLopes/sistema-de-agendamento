import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import iniciar_escrita
from app.repositories import agendamentos
from app.services.notificacao_service import (
    DadosAgendamento,
    Notificador,
    notificar_sem_falhar,
)

log = logging.getLogger(__name__)

INTERVALO_VERIFICACAO_SEGUNDOS = 60


def enviar_lembretes(
    session: Session, notificador: Notificador, agora: datetime, horas: int
) -> int:
    """Envia o lembrete dos agendamentos que começam nas próximas `horas`.

    Primeiro marca `lembrete_enviado_em` e grava (sob bloqueio de escrita), depois envia:
    assim dois processos nunca mandam o mesmo lembrete, e uma falha no envio não repete.
    """
    if horas <= 0:
        return 0
    iniciar_escrita(session)
    pendentes = agendamentos.listar_para_lembrete(session, agora, agora + timedelta(hours=horas))
    envios: list[DadosAgendamento] = []
    for agendamento, cliente, barbeiro, servico, preco in pendentes:
        agendamento.lembrete_enviado_em = agora
        envios.append(
            DadosAgendamento(
                email=cliente.email,
                cliente=cliente.nome,
                barbeiro=barbeiro,
                servico=servico,
                inicio=agendamento.inicio,
                preco=preco,
                agendamento_id=agendamento.id,
                codigo_cancelamento=agendamento.codigo_cancelamento,
            )
        )
    session.commit()
    for dados in envios:
        notificar_sem_falhar(notificador, "enviar_lembrete", dados)
    return len(envios)


class AgendadorDeLembretes:
    """Thread leve que roda `enviar_lembretes` de minuto em minuto."""

    def __init__(
        self,
        fabrica_de_sessao: Callable[[], Session],
        notificador: Notificador,
        agora: Callable[[], datetime],
        horas: int,
    ) -> None:
        self._fabrica = fabrica_de_sessao
        self._notificador = notificador
        self._agora = agora
        self._horas = horas
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._executar, name="lembretes", daemon=True)

    def iniciar(self) -> None:
        if self._horas > 0:
            self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def _executar(self) -> None:
        while not self._parar.is_set():
            try:
                with self._fabrica() as sessao:
                    enviar_lembretes(sessao, self._notificador, self._agora(), self._horas)
            except Exception:
                log.exception("falha ao processar lembretes")
            self._parar.wait(INTERVALO_VERIFICACAO_SEGUNDOS)
