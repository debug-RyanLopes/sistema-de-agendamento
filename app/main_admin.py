from fastapi import FastAPI

from app.aplicacao import criar_aplicacao
from app.config import CONFIG, USUARIO_ADMIN
from app.routers import agendamentos, cadastros, disponibilidades, gestao_barbeiros
from app.seguranca import SenhaBasicaMiddleware


def criar_app(senha: str | None = None) -> FastAPI:
    senha = senha or CONFIG.admin_password
    if not senha:
        raise RuntimeError(
            "Defina a variável de ambiente ADMIN_PASSWORD para iniciar a área da empresa."
        )
    return criar_aplicacao(
        titulo="Barbearia - Área da Empresa",
        descricao="Agendamentos marcados e cadastros de clientes, barbeiros, serviços e produtos. "
        "Acesso protegido por senha.",
        routers=[
            agendamentos.router,
            cadastros.clientes,
            cadastros.barbeiros,
            gestao_barbeiros.router,
            cadastros.servicos,
            cadastros.produtos,
            disponibilidades.router,
        ],
        pasta_front_end="admin",
        middlewares=[
            (
                SenhaBasicaMiddleware,
                {"usuario": USUARIO_ADMIN, "senha": senha, "realm": "Barbearia - Empresa"},
            )
        ],
    )
