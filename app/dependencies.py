from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.notificacao_service import LogNotificador, Notificador

_NOTIFICADOR_PADRAO = LogNotificador()


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def get_agora() -> datetime:
    return datetime.now()


def get_notificador() -> Notificador:
    return _NOTIFICADOR_PADRAO


SessaoDep = Annotated[Session, Depends(get_db)]
AgoraDep = Annotated[datetime, Depends(get_agora)]
NotificadorDep = Annotated[Notificador, Depends(get_notificador)]
