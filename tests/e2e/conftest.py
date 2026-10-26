import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")

RAIZ = Path(__file__).resolve().parents[2]
SENHA = "senha-e2e"
CABECALHO = {"Authorization": "Basic " + base64.b64encode(f"admin:{SENHA}".encode()).decode()}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


def _porta_livre() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def requisicao(base: str, metodo: str, caminho: str, corpo: dict | None = None, auth=True):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cabecalhos = {"Content-Type": "application/json", **(CABECALHO if auth else {})}
    pedido = urllib.request.Request(base + caminho, data=dados, method=metodo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            return resposta.status, json.loads(resposta.read() or "null")
    except urllib.error.HTTPError as erro:
        return erro.code, None
    except urllib.error.URLError:
        # servidor ainda não aceitou conexões: quem chama decide se tenta de novo
        return 0, None


def _aguardar(base: str) -> None:
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        status, _ = requisicao(base, "GET", "/openapi.json")
        if status == 200:
            return
        time.sleep(0.3)
    raise RuntimeError(f"servidor não respondeu: {base}")


@dataclass
class Servidores:
    cliente: str
    empresa: str


@pytest.fixture(scope="session")
def servidores() -> Iterator[Servidores]:
    pasta = tempfile.mkdtemp(prefix="e2e-barbearia-")
    banco = (Path(pasta) / "e2e.db").as_posix()
    ambiente = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{banco}",
        "ADMIN_PASSWORD": SENHA,
        "PYTHONUTF8": "1",
    }
    portas = {"cliente": _porta_livre(), "empresa": _porta_livre()}
    modulos = {"cliente": "app.main_cliente:criar_app", "empresa": "app.main_admin:criar_app"}
    processos = [
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", modulos[nome], "--factory", "--port", str(porta)],
            cwd=RAIZ,
            env=ambiente,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for nome, porta in portas.items()
    ]
    urls = Servidores(
        cliente=f"http://127.0.0.1:{portas['cliente']}",
        empresa=f"http://127.0.0.1:{portas['empresa']}",
    )
    try:
        _aguardar(urls.cliente)
        _aguardar(urls.empresa)
        yield urls
    finally:
        for processo in processos:
            processo.terminate()
        for processo in processos:
            processo.wait(timeout=10)


@pytest.fixture(scope="session")
def navegador() -> Iterator:
    with playwright_sync.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            try:
                browser = pw.chromium.launch()
            except Exception:
                pytest.skip("nenhum navegador: instale o Chrome ou `playwright install chromium`")
        yield browser
        browser.close()


@pytest.fixture
def erros_de_js() -> list[str]:
    return []


def _abrir(navegador, erros: list[str], **opcoes):
    contexto = navegador.new_context(**opcoes)
    pagina = contexto.new_page()
    pagina.on("pageerror", lambda erro: erros.append(f"pageerror: {erro}"))
    pagina.on(
        "console",
        lambda msg: (
            erros.append(f"console: {msg.text}")
            if msg.type == "error" and "status of 4" not in msg.text
            else None
        ),
    )
    pagina.on("dialog", lambda dialogo: dialogo.accept())
    return contexto, pagina


@pytest.fixture
def pagina_cliente(navegador, servidores: Servidores, erros_de_js: list[str]) -> Iterator:
    contexto, pagina = _abrir(navegador, erros_de_js, timezone_id="America/Sao_Paulo")
    pagina.goto(servidores.cliente + "/")
    yield pagina
    contexto.close()
    assert erros_de_js == []


@pytest.fixture
def pagina_empresa(navegador, servidores: Servidores, erros_de_js: list[str]) -> Iterator:
    """Entra pela página de login (cookie de sessão), como a empresa faz de verdade."""
    contexto, pagina = _abrir(navegador, erros_de_js)
    pagina.goto(servidores.empresa + "/")
    pagina.wait_for_url("**/entrar")
    pagina.fill("#login", "admin")
    pagina.fill("#senha", SENHA)
    pagina.click("#form-entrar button[type=submit]")
    pagina.wait_for_url(servidores.empresa + "/")
    yield pagina
    contexto.close()
    assert erros_de_js == []


@dataclass
class Barbearia:
    barbeiro: str
    servico: str
    barbeiro_id: int
    servico_id: int


@pytest.fixture
def barbearia(servidores: Servidores) -> Barbearia:
    """Barbeiro e serviço novos (nomes únicos), com agenda aberta o dia todo, todos os dias."""
    sufixo = uuid.uuid4().hex[:6]
    base = servidores.empresa
    _, barbeiro = requisicao(
        base, "POST", "/barbeiros", {"nome": f"Barbeiro {sufixo}", "email": f"b{sufixo}@e2e.com"}
    )
    _, servico = requisicao(
        base,
        "POST",
        "/servicos",
        {"nome": f"Corte {sufixo}", "duracao_minutos": 15, "preco": "45.00"},
    )
    for dia in range(7):
        requisicao(
            base,
            "POST",
            f"/barbeiros/{barbeiro['id']}/disponibilidades",
            {"dia_semana": dia, "hora_inicio": "00:00:00", "hora_fim": "23:59:00"},
        )
    return Barbearia(barbeiro["nome"], servico["nome"], barbeiro["id"], servico["id"])
