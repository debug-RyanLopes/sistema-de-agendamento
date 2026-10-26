from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse

from app.config import CONFIG
from app.dependencies import ChaveDep, DonoDep, SessaoDep, SomenteDono, UsuarioDep
from app.errors import NaoAutorizadoError
from app.models import Usuario
from app.schemas import (
    ERRO_401,
    ERRO_403,
    ERRO_404,
    ERRO_409,
    ERRO_422,
    AtivoIn,
    LoginIn,
    SenhaIn,
    UsuarioIn,
    UsuarioOut,
)
from app.seguranca import COOKIE_SESSAO, gerar_cookie_de_sessao
from app.services import auth_service
from app.services.auth_service import DURACAO_SESSAO_SEGUNDOS, UsuarioAutenticado

router = APIRouter(prefix="/auth", tags=["sessão"])
usuarios = APIRouter(prefix="/usuarios", tags=["usuários"], dependencies=[SomenteDono])
paginas = APIRouter(include_in_schema=False)

PAGINA_ENTRAR = Path(__file__).resolve().parent.parent / "static" / "admin" / "entrar.html"


@paginas.get("/entrar")
def pagina_de_login() -> FileResponse:
    return FileResponse(PAGINA_ENTRAR, media_type="text/html")


def _saida(usuario: UsuarioAutenticado) -> UsuarioOut:
    return UsuarioOut(
        id=usuario.id,
        nome=usuario.nome,
        login=usuario.login,
        papel=usuario.papel,
        barbeiro_id=usuario.barbeiro_id,
        ativo=True,
    )


@router.post(
    "/login",
    response_model=UsuarioOut,
    responses=ERRO_401,
    summary="Entrar com login e senha; devolve o cookie de sessão",
)
def login(
    dados: LoginIn, request: Request, resposta: Response, sessao: SessaoDep, chave: ChaveDep
) -> UsuarioOut:
    # A senha inicial é a mesma que a aplicação recebeu ao subir (ADMIN_PASSWORD ou argumento).
    senha_inicial = getattr(request.app.state, "senha_inicial", CONFIG.admin_password)
    usuario = auth_service.autenticar(sessao, dados.login, dados.senha, senha_inicial)
    if usuario is None:
        raise NaoAutorizadoError("login ou senha incorretos")
    resposta.set_cookie(
        COOKIE_SESSAO,
        gerar_cookie_de_sessao(chave, usuario),
        max_age=DURACAO_SESSAO_SEGUNDOS,
        httponly=True,
        samesite="lax",
        secure=CONFIG.url_publica.startswith("https"),
    )
    return _saida(usuario)


@router.post("/logout", status_code=204, summary="Sair (apaga o cookie)")
def logout(resposta: Response) -> Response:
    resposta.delete_cookie(COOKIE_SESSAO)
    resposta.status_code = 204
    return resposta


@router.get("/eu", response_model=UsuarioOut, responses=ERRO_401, summary="Quem está logado")
def eu(usuario: UsuarioDep) -> UsuarioOut:
    return _saida(usuario)


@usuarios.get("", response_model=list[UsuarioOut], summary="Listar usuários")
def listar_usuarios(sessao: SessaoDep) -> list[Usuario]:
    return auth_service.listar(sessao)


@usuarios.post(
    "",
    response_model=UsuarioOut,
    status_code=201,
    responses={**ERRO_403, **ERRO_404, **ERRO_409, **ERRO_422},
    summary="Criar usuário (dono ou barbeiro)",
)
def criar_usuario(dados: UsuarioIn, sessao: SessaoDep) -> Usuario:
    return auth_service.criar(sessao, dados)


@usuarios.patch(
    "/{usuario_id}/ativo",
    response_model=UsuarioOut,
    responses={**ERRO_401, **ERRO_403, **ERRO_404},
)
def definir_ativo(usuario_id: int, dados: AtivoIn, sessao: SessaoDep, quem: DonoDep) -> Usuario:
    return auth_service.definir_ativo(sessao, usuario_id, dados.ativo, quem)


@usuarios.put("/{usuario_id}/senha", response_model=UsuarioOut, responses={**ERRO_403, **ERRO_404})
def trocar_senha(usuario_id: int, dados: SenhaIn, sessao: SessaoDep) -> Usuario:
    return auth_service.trocar_senha(sessao, usuario_id, dados.senha)
