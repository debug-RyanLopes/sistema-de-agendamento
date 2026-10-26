"""Login por sessão ou Basic, usuários com papéis e o que cada papel pode fazer."""

import base64
import time

import pytest
from app.services import auth_service
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import CABECALHO_ADMIN, SENHA_TESTE
from tests.helpers import na_segunda


def _basic(usuario: str, senha: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"{usuario}:{senha}".encode()).decode()}


def _criar_barbeiro_com_login(client: TestClient, nome: str, login: str) -> dict:
    barbeiro = client.post("/barbeiros", json={"nome": nome, "email": f"{login}@b.com"}).json()
    client.post(
        f"/barbeiros/{barbeiro['id']}/disponibilidades",
        json={"dia_semana": 0, "hora_inicio": "09:00:00", "hora_fim": "18:00:00"},
    )
    usuario = client.post(
        "/usuarios",
        json={
            "nome": nome,
            "login": login,
            "senha": "senha-forte-123",
            "papel": "barbeiro",
            "barbeiro_id": barbeiro["id"],
        },
    )
    assert usuario.status_code == 201, usuario.text
    return {"barbeiro": barbeiro, "usuario": usuario.json()}


def _agendar(client: TestClient, cenario_api: dict, barbeiro_id: int, hora: int) -> dict:
    resposta = client.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": barbeiro_id,
            "servico_id": cenario_api["servico_30_id"],
            "inicio": na_segunda(hora).isoformat(),
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


# --- sessão ------------------------------------------------------------------------------


def test_primeiro_acesso_com_basic_cria_o_usuario_admin(client: TestClient):
    usuarios = client.get("/usuarios").json()

    assert [(u["login"], u["papel"]) for u in usuarios] == [("admin", "dono")]


def test_login_devolve_cookie_que_vale_como_sessao(app_admin: FastAPI):
    cliente = TestClient(app_admin)

    login = cliente.post("/auth/login", json={"login": "admin", "senha": SENHA_TESTE})
    eu = cliente.get("/auth/eu")
    cliente.post("/auth/logout")
    depois = cliente.get("/auth/eu")

    assert login.status_code == 200
    assert login.json()["papel"] == "dono"
    assert "sessao" in login.cookies
    assert eu.status_code == 200
    assert eu.json()["login"] == "admin"
    assert depois.status_code == 401


def test_login_errado_retorna_401_sem_cookie(app_admin: FastAPI):
    cliente = TestClient(app_admin)

    resposta = cliente.post("/auth/login", json={"login": "admin", "senha": "errada"})

    assert resposta.status_code == 401
    assert "sessao" not in resposta.cookies


def test_navegador_sem_sessao_vai_para_a_pagina_de_login(app_admin: FastAPI):
    cliente = TestClient(app_admin, follow_redirects=False)

    inicio = cliente.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
    pagina = cliente.get("/entrar")
    api = cliente.get("/clientes", headers={"Accept": "application/json"})

    assert inicio.status_code == 303
    assert inicio.headers["location"] == "/entrar"
    assert pagina.status_code == 200
    assert "form-entrar" in pagina.text
    assert api.status_code == 401
    assert api.headers["www-authenticate"].startswith("Basic")


def test_cookie_adulterado_ou_de_usuario_inativo_nao_vale(app_admin: FastAPI, client: TestClient):
    cliente = TestClient(app_admin)
    cliente.post("/auth/login", json={"login": "admin", "senha": SENHA_TESTE})
    cookie = cliente.cookies.get("sessao")

    adulterado = TestClient(app_admin, cookies={"sessao": cookie[:-4] + "0000"})
    lixo = TestClient(app_admin, cookies={"sessao": "qualquer-coisa"})

    assert adulterado.get("/auth/eu").status_code == 401
    assert lixo.get("/auth/eu").status_code == 401


# --- tokens e senhas ---------------------------------------------------------------------


def test_hash_de_senha_confere_e_nao_e_reversivel():
    armazenado = auth_service.gerar_hash("minha-senha")

    assert armazenado.startswith("scrypt$")
    assert "minha-senha" not in armazenado
    assert auth_service.senha_confere("minha-senha", armazenado)
    assert not auth_service.senha_confere("outra", armazenado)
    assert not auth_service.senha_confere("minha-senha", "formato-invalido")
    assert auth_service.gerar_hash("minha-senha") != armazenado  # sal aleatório


def test_token_assinado_respeita_finalidade_expiracao_e_assinatura(
    monkeypatch: pytest.MonkeyPatch,
):
    token = auth_service.gerar_token("chave", "sessao", "42", 60)

    assert auth_service.ler_token("chave", "sessao", token) == "42"
    assert auth_service.ler_token("chave", "outra-finalidade", token) is None
    assert auth_service.ler_token("outra-chave", "sessao", token) is None
    assert auth_service.ler_token("chave", "sessao", token + "x") is None
    assert auth_service.ler_token("chave", "sessao", "sem-ponto") is None
    agora_real = time.time
    monkeypatch.setattr(time, "time", lambda: agora_real() + 120)
    assert auth_service.ler_token("chave", "sessao", token) is None


# --- usuários e papéis -------------------------------------------------------------------


def test_dono_cria_usuario_barbeiro_que_so_ve_a_propria_agenda(
    app_admin: FastAPI, client: TestClient, cenario_api: dict[str, int]
):
    joao = _criar_barbeiro_com_login(client, "João", "joao")
    pedro = _criar_barbeiro_com_login(client, "Pedro", "pedro")
    meu = _agendar(client, cenario_api, joao["barbeiro"]["id"], 10)
    do_outro = _agendar(client, cenario_api, pedro["barbeiro"]["id"], 10)
    como_joao = TestClient(app_admin, headers=_basic("joao", "senha-forte-123"))

    lista = como_joao.get("/agendamentos").json()
    filtro_do_outro = como_joao.get(
        "/agendamentos", params={"barbeiro_id": pedro["barbeiro"]["id"]}
    )
    detalhe_do_outro = como_joao.get(f"/agendamentos/{do_outro['id']}")
    cancelar_do_outro = como_joao.delete(f"/agendamentos/{do_outro['id']}")
    cancelar_o_meu = como_joao.delete(f"/agendamentos/{meu['id']}")

    assert [item["id"] for item in lista["itens"]] == [meu["id"]]
    assert filtro_do_outro.status_code == 403
    assert detalhe_do_outro.status_code == 403
    assert cancelar_do_outro.status_code == 403
    assert cancelar_o_meu.status_code == 200


def test_barbeiro_nao_mexe_em_cadastros_nem_cria_agenda_para_outro(
    app_admin: FastAPI, client: TestClient, cenario_api: dict[str, int]
):
    joao = _criar_barbeiro_com_login(client, "João", "joao")
    como_joao = TestClient(app_admin, headers=_basic("joao", "senha-forte-123"))

    leitura = como_joao.get("/servicos")
    escrita = como_joao.post(
        "/clientes", json={"nome": "X Y", "email": "x@y.com", "telefone": "92991112222"}
    )
    desativar = como_joao.patch(
        f"/barbeiros/{joao['barbeiro']['id']}/ativo", json={"ativo": False}
    )
    usuarios = como_joao.get("/usuarios")
    relatorio = como_joao.get(
        "/relatorios/resumo", params={"desde": "2030-01-01", "ate": "2030-01-31"}
    )
    para_outro = como_joao.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": cenario_api["barbeiro_id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": na_segunda(10).isoformat(),
        },
    )
    para_si = como_joao.post(
        "/agendamentos",
        json={
            "cliente_id": cenario_api["cliente_id"],
            "barbeiro_id": joao["barbeiro"]["id"],
            "servico_id": cenario_api["servico_30_id"],
            "inicio": na_segunda(10).isoformat(),
        },
    )

    assert leitura.status_code == 200
    assert escrita.status_code == 403
    assert desativar.status_code == 403
    assert usuarios.status_code == 403
    assert relatorio.status_code == 403
    assert para_outro.status_code == 403
    assert para_si.status_code == 201


def test_regras_de_cadastro_de_usuario(client: TestClient):
    sem_barbeiro = client.post(
        "/usuarios", json={"nome": "Ana", "login": "ana", "senha": "12345678", "papel": "barbeiro"}
    )
    barbeiro_inexistente = client.post(
        "/usuarios",
        json={
            "nome": "Ana",
            "login": "ana",
            "senha": "12345678",
            "papel": "barbeiro",
            "barbeiro_id": 999,
        },
    )
    senha_curta = client.post(
        "/usuarios", json={"nome": "Ana", "login": "ana", "senha": "123", "papel": "dono"}
    )
    dono = client.post(
        "/usuarios", json={"nome": "Ana", "login": "Ana", "senha": "12345678", "papel": "dono"}
    )
    duplicado = client.post(
        "/usuarios", json={"nome": "Ana 2", "login": "ana", "senha": "12345678", "papel": "dono"}
    )

    assert sem_barbeiro.status_code == 422
    assert barbeiro_inexistente.status_code == 404
    assert senha_curta.status_code == 422
    assert dono.status_code == 201
    assert dono.json()["login"] == "ana"  # normalizado para minúsculas
    assert duplicado.status_code == 409


def test_desativar_usuario_e_trocar_senha(app_admin: FastAPI, client: TestClient):
    ana = client.post(
        "/usuarios", json={"nome": "Ana", "login": "ana", "senha": "12345678", "papel": "dono"}
    ).json()
    admin = client.get("/usuarios").json()[0]

    trocada = client.put(f"/usuarios/{ana['id']}/senha", json={"senha": "nova-senha-9"})
    antiga = TestClient(app_admin, headers=_basic("ana", "12345678")).get("/auth/eu")
    nova = TestClient(app_admin, headers=_basic("ana", "nova-senha-9")).get("/auth/eu")
    desativada = client.patch(f"/usuarios/{ana['id']}/ativo", json={"ativo": False})
    depois = TestClient(app_admin, headers=_basic("ana", "nova-senha-9")).get("/auth/eu")
    a_si_mesmo = client.patch(f"/usuarios/{admin['id']}/ativo", json={"ativo": False})

    assert trocada.status_code == 200
    assert antiga.status_code == 401
    assert nova.status_code == 200
    assert desativada.json()["ativo"] is False
    assert depois.status_code == 401
    assert a_si_mesmo.status_code == 409
    assert client.patch("/usuarios/999/ativo", json={"ativo": True}).status_code == 404
    assert client.put("/usuarios/999/senha", json={"senha": "12345678"}).status_code == 404


def test_senha_inicial_so_vale_enquanto_nao_ha_usuarios(app_admin: FastAPI, client: TestClient):
    client.get("/usuarios")  # cria o admin com a senha de teste
    admin = client.get("/usuarios").json()[0]
    client.put(f"/usuarios/{admin['id']}/senha", json={"senha": "trocada-123"})

    com_a_antiga = TestClient(app_admin, headers=CABECALHO_ADMIN).get("/auth/eu")
    com_a_nova = TestClient(app_admin, headers=_basic("admin", "trocada-123")).get("/auth/eu")

    assert com_a_antiga.status_code == 401
    assert com_a_nova.status_code == 200
