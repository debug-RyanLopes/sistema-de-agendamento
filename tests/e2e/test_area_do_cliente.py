import re
import uuid

import pytest
from app.tempo import agora_local, ultimo_dia_do_mes

from tests.e2e.conftest import Barbearia, Servidores, requisicao


def _marcar(pagina, barbearia: Barbearia, nome: str = "Maria E2E") -> str:
    email = f"{uuid.uuid4().hex[:8]}@e2e.com"
    pagina.reload()
    pagina.wait_for_selector(f"#servicos input[value='{barbearia.servico_id}']", state="attached")
    pagina.fill("#nome", nome)
    pagina.fill("#email", email)
    pagina.fill("#telefone", "92999998888")
    assert pagina.input_value("#telefone") == "(92) 99999-8888"  # máscara aplicada ao digitar
    pagina.check(f"#servicos input[value='{barbearia.servico_id}']")
    pagina.click("#ver-barbeiros")
    cartao = pagina.locator("article.barbeiro", has_text=barbearia.barbeiro)
    try:
        cartao.wait_for(timeout=5000)
    except Exception:
        pytest.skip("sem horários livres hoje (fim do mês ou fim do dia)")
    cartao.locator("button").first.click()
    pagina.click("#confirmar")
    pagina.locator("#confirmacao").wait_for(state="visible")
    return email


def _esperar_mensagem(pagina, trecho: str) -> None:
    pagina.wait_for_function(
        "trecho => document.querySelector('#mensagem').textContent.includes(trecho)", arg=trecho
    )


def test_cliente_marca_ve_a_confirmacao_e_a_empresa_enxerga(
    pagina_cliente, servidores: Servidores, barbearia: Barbearia
):
    _marcar(pagina_cliente, barbearia, nome="Marcos Fluxo")

    assert re.fullmatch(r"#\d+", pagina_cliente.inner_text("#conf-id"))
    assert pagina_cliente.inner_text("#conf-barbeiro") == barbearia.barbeiro
    assert pagina_cliente.inner_text("#conf-preco") == "R$ 45,00"
    assert len(pagina_cliente.inner_text("#conf-codigo")) >= 8

    status, pagina = requisicao(
        servidores.empresa, "GET", f"/agendamentos?barbeiro_id={barbearia.barbeiro_id}"
    )
    assert status == 200
    assert pagina["total"] == 1


def test_cliente_cancela_pelo_botao_e_a_empresa_ve_cancelado(
    pagina_cliente, servidores: Servidores, barbearia: Barbearia
):
    _marcar(pagina_cliente, barbearia)
    id_agendamento = int(pagina_cliente.inner_text("#conf-id").lstrip("#"))

    pagina_cliente.click("#cancelar-agendamento")
    pagina_cliente.locator("#confirmacao").wait_for(state="hidden")

    assert "cancelado" in pagina_cliente.inner_text("#mensagem")
    _, agendamento = requisicao(servidores.empresa, "GET", f"/agendamentos/{id_agendamento}")
    assert agendamento["status"] == "cancelado"


def test_recarregar_a_pagina_mantem_a_confirmacao(pagina_cliente, barbearia: Barbearia):
    _marcar(pagina_cliente, barbearia)
    codigo = pagina_cliente.inner_text("#conf-codigo")

    pagina_cliente.reload()

    assert pagina_cliente.is_visible("#confirmacao")
    assert pagina_cliente.inner_text("#conf-codigo") == codigo


def test_cancelar_com_numero_e_codigo(
    pagina_cliente, servidores: Servidores, barbearia: Barbearia
):
    _marcar(pagina_cliente, barbearia)
    id_agendamento = pagina_cliente.inner_text("#conf-id").lstrip("#")
    codigo = pagina_cliente.inner_text("#conf-codigo")
    pagina_cliente.evaluate("localStorage.clear()")
    pagina_cliente.reload()

    pagina_cliente.click(".cancelar-codigo summary")
    pagina_cliente.fill("#codigo-id", id_agendamento)
    pagina_cliente.fill("#codigo-valor", "codigo-errado")
    pagina_cliente.click("#form-cancelar-codigo button[type=submit]")
    _esperar_mensagem(pagina_cliente, "Erro 404")

    pagina_cliente.fill("#codigo-valor", codigo)
    pagina_cliente.click("#form-cancelar-codigo button[type=submit]")
    _esperar_mensagem(pagina_cliente, "cancelado")

    _, agendamento = requisicao(servidores.empresa, "GET", f"/agendamentos/{id_agendamento}")
    assert agendamento["status"] == "cancelado"


def test_confirmar_fica_desabilitado_ate_escolher_um_horario(pagina_cliente):
    assert pagina_cliente.is_disabled("#confirmar")


def test_data_so_aceita_de_hoje_ate_o_fim_do_mes_no_fuso_da_barbearia(pagina_cliente):
    hoje = agora_local().date()

    assert pagina_cliente.get_attribute("#data", "min") == hoje.isoformat()
    assert pagina_cliente.get_attribute("#data", "max") == ultimo_dia_do_mes(hoje).isoformat()


def test_servidor_recusa_data_fora_da_janela_mesmo_sem_o_navegador(
    servidores: Servidores, barbearia: Barbearia
):
    ano = agora_local().year + 1

    status, _ = requisicao(
        servidores.cliente,
        "GET",
        f"/disponibilidade?data={ano}-01-15&servico_id={barbearia.servico_id}",
        auth=False,
    )

    assert status == 422


def test_pagina_do_cliente_nao_mostra_nada_da_empresa(pagina_cliente):
    texto = pagina_cliente.inner_text("body")

    assert "Painel da Empresa" not in texto
    assert "Produtos" not in texto


@pytest.mark.parametrize("largura", [390, 1280])
def test_sem_rolagem_horizontal(pagina_cliente, largura: int):
    pagina_cliente.set_viewport_size({"width": largura, "height": 800})

    sobra = pagina_cliente.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )

    assert sobra <= 0


def test_email_invalido_mostra_erro_embaixo_do_campo_antes_de_enviar(pagina_cliente):
    pagina_cliente.fill("#email", "sem-arroba")
    pagina_cliente.dispatch_event("#email", "blur")

    erro = pagina_cliente.locator("#email ~ .erro-campo")
    erro.wait_for()

    assert "inválido" in erro.inner_text()
    assert pagina_cliente.evaluate("document.querySelector('#email').checkValidity()") is False


def test_combo_soma_duracao_na_tela(pagina_cliente, servidores: Servidores, barbearia: Barbearia):
    _, barba = requisicao(
        servidores.empresa,
        "POST",
        "/servicos",
        {"nome": f"Barba {uuid.uuid4().hex[:6]}", "duracao_minutos": 30, "preco": "30.00"},
    )
    pagina_cliente.reload()
    pagina_cliente.wait_for_selector(f"#servicos input[value='{barba['id']}']", state="attached")

    pagina_cliente.check(f"#servicos input[value='{barbearia.servico_id}']")
    pagina_cliente.check(f"#servicos input[value='{barba['id']}']")

    resumo = pagina_cliente.inner_text("#resumo-servicos")
    assert "45 min" in resumo
    assert "R$ 75,00" in resumo
