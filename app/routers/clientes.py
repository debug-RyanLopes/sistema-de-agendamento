from fastapi import APIRouter

from app.dependencies import SessaoDep
from app.models import Cliente
from app.schemas import ERRO_404, ERRO_422, ClienteIn, ClienteOut
from app.services import cadastro_service

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.post("", response_model=ClienteOut, status_code=201, responses=ERRO_422)
def criar_cliente(dados: ClienteIn, sessao: SessaoDep) -> Cliente:
    return cadastro_service.criar(sessao, Cliente, dados)


@router.get("", response_model=list[ClienteOut])
def listar_clientes(sessao: SessaoDep) -> list[Cliente]:
    return cadastro_service.listar(sessao, Cliente)


@router.get("/{cliente_id}", response_model=ClienteOut, responses=ERRO_404)
def obter_cliente(cliente_id: int, sessao: SessaoDep) -> Cliente:
    return cadastro_service.obter(sessao, Cliente, cliente_id, "cliente")
