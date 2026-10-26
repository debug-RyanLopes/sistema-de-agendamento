import os
import signal
import subprocess
import sys
import time

HOST = os.getenv("HOST", "127.0.0.1")
PORTA_CLIENTE = int(os.getenv("PORTA_CLIENTE", "8000"))
PORTA_ADMIN = int(os.getenv("PORTA_ADMIN", "8001"))
SEGUNDOS_PARA_ENCERRAR = 8

APLICACOES = [
    ("cliente", "app.main_cliente:criar_app", PORTA_CLIENTE),
    ("empresa", "app.main_admin:criar_app", PORTA_ADMIN),
]


def _iniciar(modulo: str, porta: int) -> subprocess.Popen:
    comando = [
        sys.executable,
        "-m",
        "uvicorn",
        modulo,
        "--factory",
        "--host",
        HOST,
        "--port",
        str(porta),
    ]
    opcoes = {}
    if os.name == "nt":
        opcoes["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(comando, **opcoes)


def _pedir_encerramento(processo: subprocess.Popen) -> None:
    if processo.poll() is not None:
        return
    if os.name == "nt":
        processo.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        processo.terminate()


def _encerrar(processos: list[subprocess.Popen]) -> None:
    for processo in processos:
        _pedir_encerramento(processo)
    limite = time.monotonic() + SEGUNDOS_PARA_ENCERRAR
    for processo in processos:
        try:
            processo.wait(timeout=max(0.1, limite - time.monotonic()))
        except subprocess.TimeoutExpired:
            processo.kill()


def main() -> int:
    if os.name == "nt":
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    print(f"Cliente: http://{HOST}:{PORTA_CLIENTE}/   Empresa: http://{HOST}:{PORTA_ADMIN}/")
    print("Ctrl+C encerra os dois.")
    processos = [_iniciar(modulo, porta) for _, modulo, porta in APLICACOES]
    try:
        while all(processo.poll() is None for processo in processos):
            time.sleep(0.5)
        print("Um dos servidores parou; encerrando o outro.")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        _encerrar(processos)


if __name__ == "__main__":
    raise SystemExit(main())
