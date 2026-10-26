from datetime import datetime

from app.services.notificacao_service import DadosAgendamento


def _escapar(texto: str) -> str:
    for original, escapado in (("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n")):
        texto = texto.replace(original, escapado)
    return texto


def _carimbo(momento: datetime) -> str:
    return momento.strftime("%Y%m%dT%H%M%S")


def gerar_ics(dados: DadosAgendamento, fim: datetime, fuso: str, agora: datetime) -> str:
    """Evento iCalendar com horário local da barbearia (TZID), para importar na agenda."""
    descricao = f"Agendamento #{dados.agendamento_id}. Valor R$ {dados.preco:.2f}."
    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Barbearia//Agendamento//PT-BR",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:agendamento-{dados.agendamento_id}@barbearia",
        f"DTSTAMP:{_carimbo(agora)}Z",
        f"DTSTART;TZID={fuso}:{_carimbo(dados.inicio)}",
        f"DTEND;TZID={fuso}:{_carimbo(fim)}",
        f"SUMMARY:{_escapar(f'{dados.servico} com {dados.barbeiro}')}",
        f"DESCRIPTION:{_escapar(descricao)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(linhas) + "\r\n"
