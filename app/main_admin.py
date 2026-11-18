from collections.abc import Callable

from fastapi import FastAPI

from app.aplicacao import criar_aplicacao
from app.config import CONFIG
from app.database import SessionLocal
from app.dependencies import get_db
from app.routers import (
    agendamentos,
    auth,
    cadastros,
    disponibilidades,
    gestao_barbeiros,
    relatorios,
    sistema,
    vendas,
)
from app.seguranca import AutenticacaoMiddleware
from app.services import auth_service
from app.services.lembrete_service import AgendadorDeLembretes
from app.services.notificacao_service import criar_notificador
from app.tempo import agora_local


def _iniciar_lembretes() -> Callable[[], None]:
    agendador = AgendadorDeLembretes(
        SessionLocal, criar_notificador(CONFIG), agora_local, CONFIG.lembrete_horas
    )
    agendador.iniciar()
    return agendador.parar


def _criar_usuario_inicial(senha: str) -> Callable[[], Callable[[], None]]:
    def iniciar() -> Callable[[], None]:
        with SessionLocal() as sessao:
            auth_service.garantir_usuario_inicial(sessao, senha)
        return lambda: None

    return iniciar


def criar_app(senha: str | None = None, *, lembretes: bool = True) -> FastAPI:
    senha = senha or CONFIG.admin_password
    if not senha:
        raise RuntimeError(
            "Defina a variável de ambiente ADMIN_PASSWORD para iniciar a área da empresa."
        )
    inicializadores = [_criar_usuario_inicial(senha)]
    if lembretes:
        inicializadores.append(_iniciar_lembretes)
    aplicacao = criar_aplicacao(
        titulo="Barbearia - Área da Empresa",
        descricao="Agendamentos, cadastros, disponibilidade, bloqueios, vendas e relatórios. "
        "Acesso por login e senha (sessão) ou HTTP Basic.",
        routers=[
            auth.paginas,
            auth.router,
            auth.usuarios,
            agendamentos.router,
            cadastros.clientes,
            cadastros.barbeiros,
            gestao_barbeiros.router,
            cadastros.servicos,
            cadastros.produtos,
            disponibilidades.router,
            disponibilidades.bloqueios,
            vendas.router,
            relatorios.router,
            sistema.router,
        ],
        pasta_front_end="admin",
        middlewares=[
            (
                AutenticacaoMiddleware,
                {
                    "senha_inicial": senha,
                    "chave": CONFIG.secret_key,
                    "realm": "Barbearia - Empresa",
                    "obter_sessao": get_db,
                },
            )
        ],
        inicializadores=inicializadores,
    )
    aplicacao.state.senha_inicial = senha
    return aplicacao
