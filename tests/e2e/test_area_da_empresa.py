import uuid
from datetime import timedelta

import pytest

from app.tempo import agora_local
from tests.e2e.conftest import Barbearia, Servidores, requisicao


def _aba(pagina, nome: str) -> None:
    pagina.click(f'button[data-aba="{nome}"]')
    pagina.locator(f"#aba-{nome}").wait_for(state="visible")


def _cadastrar(pagina, aba: str, **campos: str) -> None:
    _aba(pagina, aba)
    for nome, valor in campos.items():
        pagina.fill(f"#aba-{aba} input[name={nome}]", valor)
    pagina.click(f"#aba-{aba} form button[type=submit]")


def _esperar_mensagem(pagina, trecho: str) -> None:
    pagina.wait_for_function(
        "trecho => document.querySelector('#mensagem').textContent.includes(trecho)", arg=trecho
    )


def _linha(pagina, aba: str, texto: str):
    return pagina.locator(f"#aba-{aba} tbody tr", has_text=texto)


def _novo_cliente(servidores: Servidores, rotulo: str) -> dict:
    sufixo = uuid.uuid4().hex[:6]
    _, cliente = requisicao(
        servidores.empresa,
        "POST",
        "/clientes",
        {"nome": f"{rotulo} {sufixo}", "email": f"{sufixo}@e2e.com", "telefone": "92977776666"},
    )
    return cliente


def _agendar_em_breve(servidores: Servidores, barbearia: Barbearia, cliente: dict) -> dict:
    proximo = (agora_local() + timedelta(minutes=45)).replace(second=0, microsecond=0)
    proximo = proximo.replace(minute=proximo.minute - proximo.minute % 15)
    status, agendamento = requisicao(
        servidores.empresa,
        "POST",
        "/agendamentos",
        {
            "cliente_id": cliente["id"],
            "barbeiro_id": barbearia.barbeiro_id,
            "servico_id": barbearia.servico_id,
            "inicio": proximo.isoformat(),
        },
    )
    assert status == 201
    return agendamento


def _barbeiro_ativo(servidores: Servidores, barbearia: Barbearia) -> bool:
    return requisicao(servidores.empresa, "GET", f"/barbeiros/{barbearia.barbeiro_id}")[1]["ativo"]


def test_area_da_empresa_exige_senha(servidores: Servidores):
    status, _ = requisicao(servidores.empresa, "GET", "/", auth=False)

    assert status == 401


def test_cadastra_edita_e_desativa_cliente(pagina_empresa):
    sufixo = uuid.uuid4().hex[:6]
    email = f"{sufixo}@e2e.com"
    _cadastrar(
        pagina_empresa,
        "clientes",
        nome=f"Cliente {sufixo}",
        email=email,
        telefone="92988887777",
    )
    _esperar_mensagem(pagina_empresa, "cadastrado")
    assert _linha(pagina_empresa, "clientes", email).count() == 1

    _linha(pagina_empresa, "clientes", email).get_by_role("button", name="Editar").click()
    pagina_empresa.fill("#aba-clientes input[name=nome]", f"Editado {sufixo}")
    pagina_empresa.click("#aba-clientes form button[type=submit]")
    _linha(pagina_empresa, "clientes", f"Editado {sufixo}").wait_for()

    _linha(pagina_empresa, "clientes", email).get_by_role("button", name="Desativar").click()
    _linha(pagina_empresa, "clientes", email).wait_for(state="detached")
    pagina_empresa.check("#aba-clientes input[type=checkbox]")
    assert _linha(pagina_empresa, "clientes", email).count() == 1


def test_email_de_cliente_repetido_mostra_erro_409(pagina_empresa):
    sufixo = uuid.uuid4().hex[:6]
    dados = {"nome": f"Cliente {sufixo}", "email": f"{sufixo}@e2e.com", "telefone": "92988887777"}
    _cadastrar(pagina_empresa, "clientes", **dados)
    _esperar_mensagem(pagina_empresa, "cadastrado")

    _cadastrar(pagina_empresa, "clientes", **{**dados, "nome": "Outro Nome"})
    _esperar_mensagem(pagina_empresa, "Erro 409")

    assert "já existe" in pagina_empresa.inner_text("#mensagem")


@pytest.mark.parametrize(("digitado", "exibido"), [("12.50", "R$ 12,50"), ("7", "R$ 7,00")])
def test_cadastra_produto_com_preco_decimal(pagina_empresa, digitado: str, exibido: str):
    nome = f"Pomada {uuid.uuid4().hex[:6]}"

    _cadastrar(pagina_empresa, "produtos", nome=nome, preco=digitado, estoque="5")

    _linha(pagina_empresa, "produtos", nome).wait_for()
    assert exibido in _linha(pagina_empresa, "produtos", nome).inner_text()


def test_agendamento_aparece_na_lista_e_a_empresa_cancela(
    pagina_empresa, servidores: Servidores, barbearia: Barbearia
):
    cliente = _novo_cliente(servidores, "Cli")
    agendamento = _agendar_em_breve(servidores, barbearia, cliente)

    pagina_empresa.reload()
    pagina_empresa.select_option("#filtro-barbeiro", value=str(barbearia.barbeiro_id))
    pagina_empresa.click("#form-filtro button[type=submit]")
    linha = pagina_empresa.locator("#lista-agendamentos tr", has_text=cliente["nome"])
    linha.wait_for()
    linha.get_by_role("button", name="Cancelar").click()
    pagina_empresa.wait_for_function(
        "nome => [...document.querySelectorAll('#lista-agendamentos tr')]"
        ".some(tr => tr.textContent.includes(nome) && tr.textContent.includes('cancelado'))",
        arg=cliente["nome"],
    )

    _, depois = requisicao(servidores.empresa, "GET", f"/agendamentos/{agendamento['id']}")
    assert depois["status"] == "cancelado"


def test_lista_de_agendamentos_e_paginada(
    pagina_empresa, servidores: Servidores, barbearia: Barbearia
):
    cliente = _novo_cliente(servidores, "Paginado")
    amanha = (agora_local() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(27):
        status, _ = requisicao(
            servidores.empresa,
            "POST",
            "/agendamentos",
            {
                "cliente_id": cliente["id"],
                "barbeiro_id": barbearia.barbeiro_id,
                "servico_id": barbearia.servico_id,
                "inicio": (amanha + timedelta(minutes=15 * i)).isoformat(),
            },
        )
        assert status == 201

    pagina_empresa.reload()
    pagina_empresa.select_option("#filtro-barbeiro", value=str(barbearia.barbeiro_id))
    pagina_empresa.click("#form-filtro button[type=submit]")
    pagina_empresa.wait_for_function(
        "document.querySelector('#pag-info').textContent.includes('de 27')"
    )

    assert pagina_empresa.locator("#lista-agendamentos tr").count() == 25
    assert "1–25 de 27" in pagina_empresa.inner_text("#pag-info")
    assert pagina_empresa.is_disabled("#pag-anterior")

    pagina_empresa.click("#pag-proxima")
    pagina_empresa.wait_for_function(
        "document.querySelector('#pag-info').textContent.includes('26')"
    )

    assert pagina_empresa.locator("#lista-agendamentos tr").count() == 2
    assert pagina_empresa.is_disabled("#pag-proxima")

    pagina_empresa.click("#pag-anterior")
    pagina_empresa.wait_for_function(
        "document.querySelector('#pag-info').textContent.includes('1–')"
    )
    assert pagina_empresa.locator("#lista-agendamentos tr").count() == 25


def test_desativar_barbeiro_pede_confirmacao_e_mostra_o_impacto(
    pagina_empresa, servidores: Servidores, barbearia: Barbearia
):
    cliente = _novo_cliente(servidores, "Impacto")
    _agendar_em_breve(servidores, barbearia, cliente)

    _aba(pagina_empresa, "barbeiros")
    linha = _linha(pagina_empresa, "barbeiros", barbearia.barbeiro)
    linha.get_by_role("button", name="Desativar").click()
    dialogo = pagina_empresa.locator("#dialogo-desativar")
    dialogo.wait_for(state="visible")

    texto = dialogo.inner_text()
    assert f"Desativar {barbearia.barbeiro}?" in texto
    assert "Tempo na empresa" in texto
    assert "Atendimentos já realizados" in texto
    assert "Agendamentos futuros" in texto
    assert "R$ 45,00" in texto
    assert cliente["nome"] in texto
    assert "continuam marcados" in texto

    dialogo.get_by_role("button", name="Voltar").click()
    dialogo.wait_for(state="hidden")
    assert _barbeiro_ativo(servidores, barbearia)

    linha.get_by_role("button", name="Desativar").click()
    dialogo.wait_for(state="visible")
    dialogo.get_by_role("button", name="Desativar mesmo assim").click()
    _esperar_mensagem(pagina_empresa, "desativado")

    assert not _barbeiro_ativo(servidores, barbearia)


def test_barbeiro_desativado_some_da_area_do_cliente(
    pagina_empresa, servidores: Servidores, barbearia: Barbearia
):
    _aba(pagina_empresa, "barbeiros")
    _linha(pagina_empresa, "barbeiros", barbearia.barbeiro).get_by_role(
        "button", name="Desativar"
    ).click()
    pagina_empresa.locator("#dialogo-desativar").wait_for(state="visible")
    pagina_empresa.get_by_role("button", name="Desativar mesmo assim").click()
    _esperar_mensagem(pagina_empresa, "desativado")

    status, corpo = requisicao(
        servidores.cliente,
        "GET",
        f"/disponibilidade?data={agora_local().date()}&servico_id={barbearia.servico_id}",
        auth=False,
    )

    assert status == 200
    assert barbearia.barbeiro_id not in [b["id"] for b in corpo["barbeiros"]]


def test_desativar_barbeiro_sem_agendamentos_nao_mostra_aviso(
    pagina_empresa, barbearia: Barbearia
):
    _aba(pagina_empresa, "barbeiros")
    _linha(pagina_empresa, "barbeiros", barbearia.barbeiro).get_by_role(
        "button", name="Desativar"
    ).click()
    dialogo = pagina_empresa.locator("#dialogo-desativar")
    dialogo.wait_for(state="visible")

    assert "continuam marcados" not in dialogo.inner_text()
    assert "Agendamentos futuros" in dialogo.inner_text()
    dialogo.get_by_role("button", name="Voltar").click()
