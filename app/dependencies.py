from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import CONFIG
from app.database import SessionLocal
from app.errors import AcessoNegadoError, NaoAutorizadoError
from app.services.auth_service import UsuarioAutenticado
from app.services.notificacao_service import Notificador, criar_notificador
from app.tempo import agora_local

_NOTIFICADOR_PADRAO = criar_notificador(CONFIG)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def get_agora() -> datetime:
    return agora_local()


def get_notificador() -> Notificador:
    return _NOTIFICADOR_PADRAO


def get_chave() -> str:
    return CONFIG.secret_key


def get_usuario(request: Request) -> UsuarioAutenticado:
    usuario = getattr(request.state, "usuario", None)
    if usuario is None:
        raise NaoAutorizadoError("Autenticação necessária")
    return usuario


def exigir_dono(
    usuario: Annotated[UsuarioAutenticado, Depends(get_usuario)],
) -> UsuarioAutenticado:
    if not usuario.e_dono:
        raise AcessoNegadoError("apenas o dono da barbearia pode fazer isso")
    return usuario


SessaoDep = Annotated[Session, Depends(get_db)]
AgoraDep = Annotated[datetime, Depends(get_agora)]
NotificadorDep = Annotated[Notificador, Depends(get_notificador)]
ChaveDep = Annotated[str, Depends(get_chave)]
UsuarioDep = Annotated[UsuarioAutenticado, Depends(get_usuario)]
DonoDep = Annotated[UsuarioAutenticado, Depends(exigir_dono)]
SomenteDono = Depends(exigir_dono)
