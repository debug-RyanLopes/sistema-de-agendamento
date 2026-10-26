from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import CONFIG
from app.dependencies import SessaoDep
from app.schemas import ConfiguracaoOut

VERSAO = "3.0.0"

router = APIRouter(tags=["sistema"])


@router.get("/configuracao", response_model=ConfiguracaoOut, summary="Parâmetros públicos")
def configuracao() -> ConfiguracaoOut:
    return ConfiguracaoOut(
        fuso=CONFIG.timezone,
        slot_minutos=CONFIG.slot_minutes,
        intervalo_minutos=CONFIG.intervalo_minutos,
        max_agendamentos_ativos_por_cliente=CONFIG.max_agendamentos_ativos_por_cliente,
        versao=VERSAO,
    )


@router.get("/saude", summary="Verificação de saúde (banco acessível)")
def saude(sessao: SessaoDep) -> JSONResponse:
    try:
        sessao.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "erro", "banco": "indisponível"}, status_code=503)
    return JSONResponse({"status": "ok", "banco": "ok", "versao": VERSAO})
