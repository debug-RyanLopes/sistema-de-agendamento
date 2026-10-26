import base64
import binascii
from collections.abc import Callable, Iterator
from http.cookies import SimpleCookie

from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services import auth_service
from app.services.auth_service import DURACAO_SESSAO_SEGUNDOS, UsuarioAutenticado

COOKIE_SESSAO = "sessao"
CAMINHOS_PUBLICOS = {"/auth/login", "/entrar", "/saude"}
PREFIXOS_PUBLICOS = ("/comum/",)


def gerar_cookie_de_sessao(chave: str, usuario: UsuarioAutenticado) -> str:
    return auth_service.gerar_token(chave, "sessao", str(usuario.id), DURACAO_SESSAO_SEGUNDOS)


def _ler_basic(cabecalho: str | None) -> tuple[str, str] | None:
    if not cabecalho or not cabecalho.lower().startswith("basic "):
        return None
    try:
        decodificado = base64.b64decode(cabecalho[6:].strip(), validate=True)
    except (binascii.Error, ValueError):
        return None
    usuario, separador, senha = decodificado.partition(b":")
    if not separador:
        return None
    try:
        return usuario.decode(), senha.decode()
    except UnicodeDecodeError:
        return None


class AutenticacaoMiddleware:
    """Protege a área da empresa.

    Aceita sessão por cookie (login pela página) ou HTTP Basic (Swagger, scripts e
    testes). Usuários e senhas ficam no banco com hash scrypt; enquanto o banco não tem
    nenhum usuário, `admin` + ADMIN_PASSWORD cria o primeiro dono.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        senha_inicial: str,
        chave: str,
        realm: str,
        obter_sessao: Callable[[], Iterator[Session]],
    ) -> None:
        self.app = app
        self.senha_inicial = senha_inicial
        self.chave = chave
        self.realm = realm
        self.obter_sessao = obter_sessao

    def _com_sessao(self, scope: Scope) -> Iterator[Session]:
        # Respeita `dependency_overrides` da aplicação (é assim que os testes trocam o banco).
        aplicacao = scope.get("app")
        fabrica = self.obter_sessao
        if aplicacao is not None:
            fabrica = aplicacao.dependency_overrides.get(fabrica, fabrica)
        return fabrica()

    def _autenticar(self, scope: Scope) -> UsuarioAutenticado | None:
        cabecalhos = Headers(scope=scope)
        gerador = self._com_sessao(scope)
        sessao = next(gerador)
        try:
            cookies = SimpleCookie()
            cookies.load(cabecalhos.get("cookie", ""))
            if COOKIE_SESSAO in cookies:
                usuario_id = auth_service.ler_token(
                    self.chave, "sessao", cookies[COOKIE_SESSAO].value
                )
                if usuario_id and usuario_id.isdigit():
                    usuario = auth_service.por_id(sessao, int(usuario_id))
                    if usuario is not None:
                        return usuario
            credenciais = _ler_basic(cabecalhos.get("authorization"))
            if credenciais is not None:
                return auth_service.autenticar(sessao, *credenciais, self.senha_inicial)
            return None
        finally:
            gerador.close()

    @staticmethod
    def _e_navegacao(scope: Scope) -> bool:
        aceita = Headers(scope=scope).get("accept", "")
        return (
            scope["method"] == "GET" and "text/html" in aceita and "application/json" not in aceita
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        caminho = scope["path"]
        if caminho in CAMINHOS_PUBLICOS or caminho.startswith(PREFIXOS_PUBLICOS):
            await self.app(scope, receive, send)
            return
        usuario = self._autenticar(scope)
        if usuario is not None:
            scope.setdefault("state", {})["usuario"] = usuario
            await self.app(scope, receive, send)
            return
        if self._e_navegacao(scope):
            resposta: Response = RedirectResponse("/entrar", status_code=303)
        else:
            resposta = JSONResponse(
                {"detail": "Autenticação necessária"},
                status_code=401,
                headers={"WWW-Authenticate": f'Basic realm="{self.realm}", charset="UTF-8"'},
            )
        await resposta(scope, receive, send)
