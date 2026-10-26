from fastapi import FastAPI

from app.aplicacao import criar_aplicacao
from app.config import CONFIG
from app.limites import LimiteDeRequisicoesMiddleware
from app.routers import publico, sistema


def criar_app(limite_por_minuto: int | None = None) -> FastAPI:
    return criar_aplicacao(
        titulo="Barbearia - Área do Cliente",
        descricao="Escolha o serviço, o barbeiro e o horário, marque e, se precisar, "
        "cancele ou remarque o próprio agendamento com o código recebido.",
        routers=[publico.router, sistema.router],
        pasta_front_end="cliente",
        middlewares=[
            (
                LimiteDeRequisicoesMiddleware,
                {
                    "por_minuto": (
                        CONFIG.limite_requisicoes_por_minuto
                        if limite_por_minuto is None
                        else limite_por_minuto
                    )
                },
            )
        ],
    )
