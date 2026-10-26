import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import USUARIO_ADMIN
from app.database import iniciar_escrita
from app.errors import RecursoDuplicadoError, RecursoNaoEncontradoError, TransicaoInvalidaError
from app.models import Barbeiro, PapelUsuario, Usuario
from app.schemas import UsuarioIn
from app.services import cadastro_service

DURACAO_SESSAO_SEGUNDOS = 12 * 60 * 60
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


# --- senhas ------------------------------------------------------------------------------


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(senha.encode(), salt=sal, **_SCRYPT)
    return "scrypt$" + base64.b64encode(sal).decode() + "$" + base64.b64encode(derivada).decode()


def senha_confere(senha: str, armazenado: str) -> bool:
    try:
        esquema, sal, esperado = armazenado.split("$")
        if esquema != "scrypt":
            return False
        derivada = hashlib.scrypt(senha.encode(), salt=base64.b64decode(sal), **_SCRYPT)
        return hmac.compare_digest(derivada, base64.b64decode(esperado))
    except (ValueError, TypeError):
        return False


# --- tokens assinados (sessão e links mágicos) ------------------------------------------


def _assinar(chave: str, conteudo: bytes) -> str:
    return hmac.new(chave.encode(), conteudo, hashlib.sha256).hexdigest()


def gerar_token(chave: str, finalidade: str, assunto: str, segundos: int) -> str:
    expira = int(time.time()) + segundos
    conteudo = f"{finalidade}|{assunto}|{expira}".encode()
    return (
        base64.urlsafe_b64encode(conteudo).decode().rstrip("=") + "." + _assinar(chave, conteudo)
    )


def ler_token(chave: str, finalidade: str, token: str) -> str | None:
    """Devolve o assunto do token se a assinatura confere, a finalidade bate e não expirou."""
    try:
        corpo, assinatura = token.rsplit(".", 1)
        conteudo = base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4))
        if not hmac.compare_digest(_assinar(chave, conteudo), assinatura):
            return None
        fim, assunto, expira = conteudo.decode().split("|")
    except (ValueError, UnicodeDecodeError):
        return None
    if fim != finalidade or int(expira) < time.time():
        return None
    return assunto


# --- usuários ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UsuarioAutenticado:
    id: int
    nome: str
    login: str
    papel: PapelUsuario
    barbeiro_id: int | None

    @property
    def e_dono(self) -> bool:
        return self.papel == PapelUsuario.DONO


def _autenticado(usuario: Usuario) -> UsuarioAutenticado:
    return UsuarioAutenticado(
        usuario.id, usuario.nome, usuario.login, usuario.papel, usuario.barbeiro_id
    )


def obter_por_login(session: Session, login: str) -> Usuario | None:
    return session.scalars(select(Usuario).where(Usuario.login == login.strip().lower())).first()


def ha_usuarios(session: Session) -> bool:
    return session.scalars(select(Usuario.id).limit(1)).first() is not None


def garantir_usuario_inicial(session: Session, senha_inicial: str | None) -> None:
    """Cria o dono 'admin' com a ADMIN_PASSWORD quando o banco ainda não tem usuários."""
    if not senha_inicial or ha_usuarios(session):
        return
    # Solta a conexão de leitura para que a próxima transação já nasça em modo de escrita;
    # assim dois processos que sobem juntos não criam o usuário duas vezes nem travam.
    session.rollback()
    iniciar_escrita(session)
    if ha_usuarios(session):
        return
    session.add(
        Usuario(
            nome="Administrador",
            login=USUARIO_ADMIN,
            senha_hash=gerar_hash(senha_inicial),
            papel=PapelUsuario.DONO,
        )
    )
    session.commit()


def autenticar(
    session: Session, login: str, senha: str, senha_inicial: str | None = None
) -> UsuarioAutenticado | None:
    garantir_usuario_inicial(session, senha_inicial)
    usuario = obter_por_login(session, login)
    if usuario is None or not usuario.ativo or not senha_confere(senha, usuario.senha_hash):
        return None
    return _autenticado(usuario)


def por_id(session: Session, usuario_id: int) -> UsuarioAutenticado | None:
    usuario = session.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        return None
    return _autenticado(usuario)


def listar(session: Session) -> list[Usuario]:
    return list(session.scalars(select(Usuario).order_by(Usuario.id)))


def criar(session: Session, dados: UsuarioIn) -> Usuario:
    iniciar_escrita(session)
    login = dados.login.strip().lower()
    if obter_por_login(session, login) is not None:
        raise RecursoDuplicadoError(f"já existe um usuário com o login {login}")
    if dados.barbeiro_id is not None:
        cadastro_service.obter(session, Barbeiro, dados.barbeiro_id, "barbeiro")
    usuario = Usuario(
        nome=dados.nome,
        login=login,
        senha_hash=gerar_hash(dados.senha),
        papel=dados.papel,
        barbeiro_id=dados.barbeiro_id if dados.papel == PapelUsuario.BARBEIRO else None,
    )
    session.add(usuario)
    session.commit()
    return usuario


def _obter(session: Session, usuario_id: int) -> Usuario:
    usuario = session.get(Usuario, usuario_id)
    if usuario is None:
        raise RecursoNaoEncontradoError(f"usuário {usuario_id} não encontrado")
    return usuario


def definir_ativo(
    session: Session, usuario_id: int, ativo: bool, quem: UsuarioAutenticado
) -> Usuario:
    iniciar_escrita(session)
    usuario = _obter(session, usuario_id)
    if usuario.id == quem.id and not ativo:
        raise TransicaoInvalidaError("você não pode desativar o próprio usuário")
    usuario.ativo = ativo
    session.commit()
    return usuario


def trocar_senha(session: Session, usuario_id: int, senha: str) -> Usuario:
    iniciar_escrita(session)
    usuario = _obter(session, usuario_id)
    usuario.senha_hash = gerar_hash(senha)
    session.commit()
    return usuario
