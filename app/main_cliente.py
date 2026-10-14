from fastapi import FastAPI

from app.aplicacao import criar_aplicacao
from app.routers import publico


def criar_app() -> FastAPI:
    return criar_aplicacao(
        titulo="Barbearia - Área do Cliente",
        descricao="Escolha o serviço, o barbeiro e o horário, marque e, se precisar, "
        "cancele o próprio agendamento com o código recebido.",
        routers=[publico.router],
        pasta_front_end="cliente",
    )
