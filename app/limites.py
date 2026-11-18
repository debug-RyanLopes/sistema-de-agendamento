import time
from collections import defaultdict, deque

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

JANELA_SEGUNDOS = 60


class LimiteDeRequisicoesMiddleware:
    """Janela deslizante por IP: no máximo `por_minuto` requisições dos métodos indicados.

    Protege a área pública de scripts que tentam lotar a agenda. Em memória, por
    processo: suficiente para uma instância; com várias réplicas, use o proxy ou Redis.
    """

    def __init__(
        self, app: ASGIApp, *, por_minuto: int, metodos: tuple[str, ...] = ("POST",)
    ) -> None:
        self.app = app
        self.por_minuto = por_minuto
        self.metodos = metodos
        self._historico: dict[str, deque[float]] = defaultdict(deque)

    def _identificar(self, scope: Scope) -> str:
        encaminhado = Headers(scope=scope).get("x-forwarded-for")
        if encaminhado:
            return encaminhado.split(",")[0].strip()
        cliente = scope.get("client")
        return cliente[0] if cliente else "desconhecido"

    def _excedeu(self, chave: str) -> bool:
        agora = time.monotonic()
        fila = self._historico[chave]
        while fila and agora - fila[0] > JANELA_SEGUNDOS:
            fila.popleft()
        if len(fila) >= self.por_minuto:
            return True
        fila.append(agora)
        if len(self._historico) > 10_000:
            self._historico = defaultdict(
                deque, {k: v for k, v in self._historico.items() if v and agora - v[-1] < 300}
            )
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or self.por_minuto <= 0
            or scope["method"] not in self.metodos
            or not self._excedeu(self._identificar(scope))
        ):
            await self.app(scope, receive, send)
            return
        resposta = JSONResponse(
            {"detail": "muitas tentativas em pouco tempo; aguarde um minuto"},
            status_code=429,
            headers={"Retry-After": str(JANELA_SEGUNDOS)},
        )
        await resposta(scope, receive, send)
