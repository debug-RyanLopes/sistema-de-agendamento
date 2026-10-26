import json
import logging
from datetime import UTC, datetime


class FormatadorJson(logging.Formatter):
    """Uma linha JSON por evento, pronta para coletores de log."""

    def format(self, registro: logging.LogRecord) -> str:
        evento = {
            "momento": datetime.fromtimestamp(registro.created, UTC).isoformat(),
            "nivel": registro.levelname,
            "origem": registro.name,
            "mensagem": registro.getMessage(),
        }
        if registro.exc_info:
            evento["excecao"] = self.formatException(registro.exc_info)
        return json.dumps(evento, ensure_ascii=False)


def configurar_logging(nivel: str, em_json: bool) -> None:
    raiz = logging.getLogger()
    if getattr(raiz, "_barbearia_configurado", False):
        return
    manipulador = logging.StreamHandler()
    manipulador.setFormatter(
        FormatadorJson() if em_json else logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    )
    raiz.handlers[:] = [manipulador]
    raiz.setLevel(nivel)
    raiz._barbearia_configurado = True  # type: ignore[attr-defined]
