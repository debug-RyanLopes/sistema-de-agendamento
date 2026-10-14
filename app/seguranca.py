import base64
import binascii
import secrets

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send


class SenhaBasicaMiddleware:
    def __init__(self, app: ASGIApp, *, usuario: str, senha: str, realm: str) -> None:
        self.app = app
        self.usuario = usuario.encode()
        self.senha = senha.encode()
        self.realm = realm

    def _autorizado(self, cabecalho: str | None) -> bool:
        if not cabecalho or not cabecalho.lower().startswith("basic "):
            return False
        try:
            decodificado = base64.b64decode(cabecalho[6:].strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
        usuario, separador, senha = decodificado.partition(b":")
        usuario_ok = secrets.compare_digest(usuario, self.usuario)
        senha_ok = secrets.compare_digest(senha, self.senha)
        return bool(separador) and usuario_ok and senha_ok

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if self._autorizado(Headers(scope=scope).get("authorization")):
            await self.app(scope, receive, send)
            return
        resposta = Response(
            "Autenticação necessária",
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{self.realm}", charset="UTF-8"'},
        )
        await resposta(scope, receive, send)
