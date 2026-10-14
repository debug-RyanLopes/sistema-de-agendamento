from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import (
    ConflitoHorarioError,
    ForaDaDisponibilidadeError,
    HorarioPassadoError,
    RecursoInativoError,
    RecursoNaoEncontradoError,
)
from app.models import Agendamento, Barbeiro, Cliente, StatusAgendamento
from app.schemas import AgendamentoIn, AgendamentoPublicoIn
from app.services import agendamento_service, disponibilidade_service
from tests.conftest import Cenario
from tests.helpers import AGORA_FIXO, DOMINGO, na_segunda


def _dados(
    cenario: Cenario,
    inicio: datetime,
    email: str = "novo@exemplo.com",
    nome: str = "Maria Nova",
    telefone: str = "11911112222",
) -> AgendamentoPublicoIn:
    return AgendamentoPublicoIn(
        nome=nome,
        email=email,
        telefone=telefone,
        barbeiro_id=cenario.barbeiro.id,
        servico_id=cenario.servico_30.id,
        inicio=inicio,
    )


def _total(session: Session, modelo) -> int:
    return session.scalar(select(func.count()).select_from(modelo))


def test_cria_cliente_novo_e_gera_codigo_de_cancelamento(session: Session, cenario: Cenario):
    agendamento, confirmacao = agendamento_service.criar_publico(
        session, _dados(cenario, na_segunda(10)), AGORA_FIXO
    )

    cliente = session.get(Cliente, agendamento.cliente_id)
    assert cliente.email == "novo@exemplo.com"
    assert cliente.nome == "Maria Nova"
    assert len(agendamento.codigo_cancelamento) >= 8
    assert confirmacao.email == "novo@exemplo.com"
    assert confirmacao.barbeiro == "João Barbeiro"
    assert confirmacao.preco == 45.0


def test_codigos_de_cancelamento_sao_diferentes(session: Session, cenario: Cenario):
    primeiro, _ = agendamento_service.criar_publico(
        session, _dados(cenario, na_segunda(10)), AGORA_FIXO
    )
    segundo, _ = agendamento_service.criar_publico(
        session, _dados(cenario, na_segunda(11)), AGORA_FIXO
    )

    assert primeiro.codigo_cancelamento != segundo.codigo_cancelamento


def test_reaproveita_cliente_existente_sem_sobrescrever_dados(session: Session, cenario: Cenario):
    dados = _dados(
        cenario,
        na_segunda(10),
        email="carlos@exemplo.com",
        nome="Outro Nome",
        telefone="1100000000",
    )

    agendamento, _ = agendamento_service.criar_publico(session, dados, AGORA_FIXO)

    assert agendamento.cliente_id == cenario.cliente.id
    assert _total(session, Cliente) == 1
    session.refresh(cenario.cliente)
    assert cenario.cliente.nome == "Carlos Silva"
    assert cenario.cliente.telefone == "11987654321"


def test_cliente_inativo_nao_agenda_e_nada_e_gravado(session: Session, cenario: Cenario):
    cenario.cliente.ativo = False
    session.commit()

    with pytest.raises(RecursoInativoError):
        agendamento_service.criar_publico(
            session, _dados(cenario, na_segunda(10), email="carlos@exemplo.com"), AGORA_FIXO
        )

    assert _total(session, Agendamento) == 0


@pytest.mark.parametrize("recurso", ["barbeiro", "servico_30"])
def test_barbeiro_ou_servico_inativo_nao_agenda(
    session: Session, cenario: Cenario, recurso: str
):
    getattr(cenario, recurso).ativo = False
    session.commit()

    with pytest.raises(RecursoInativoError):
        agendamento_service.criar_publico(session, _dados(cenario, na_segunda(10)), AGORA_FIXO)

    assert _total(session, Cliente) == 1


def test_conflito_nao_deixa_cliente_novo_para_tras(session: Session, cenario: Cenario):
    agendamento_service.criar_publico(session, _dados(cenario, na_segunda(10)), AGORA_FIXO)
    clientes_antes = _total(session, Cliente)

    with pytest.raises(ConflitoHorarioError):
        agendamento_service.criar_publico(
            session, _dados(cenario, na_segunda(10), email="outro@exemplo.com"), AGORA_FIXO
        )

    assert _total(session, Cliente) == clientes_antes
    assert _total(session, Agendamento) == 1


@pytest.mark.parametrize(
    ("inicio", "erro"),
    [
        (datetime(2029, 12, 31, 10, 0), HorarioPassadoError),
        (DOMINGO.replace(hour=10), ForaDaDisponibilidadeError),
        (na_segunda(18), ForaDaDisponibilidadeError),
    ],
    ids=["passado", "domingo", "fim-da-janela"],
)
def test_regras_de_horario_valem_para_o_cliente(
    session: Session, cenario: Cenario, inicio: datetime, erro: type[Exception]
):
    with pytest.raises(erro):
        agendamento_service.criar_publico(session, _dados(cenario, inicio), AGORA_FIXO)

    assert _total(session, Cliente) == 1


def test_barbeiro_inexistente_levanta_nao_encontrado(session: Session, cenario: Cenario):
    dados = _dados(cenario, na_segunda(10)).model_copy(update={"barbeiro_id": 999})

    with pytest.raises(RecursoNaoEncontradoError):
        agendamento_service.criar_publico(session, dados, AGORA_FIXO)


def _agendar(session: Session, cenario: Cenario) -> Agendamento:
    agendamento, _ = agendamento_service.criar_publico(
        session, _dados(cenario, na_segunda(10)), AGORA_FIXO
    )
    return agendamento


def test_cancelar_com_codigo_correto(session: Session, cenario: Cenario):
    agendamento = _agendar(session, cenario)

    cancelado = agendamento_service.cancelar_com_codigo(
        session, agendamento.id, agendamento.codigo_cancelamento, AGORA_FIXO
    )

    assert cancelado.status == StatusAgendamento.CANCELADO


def test_cancelar_libera_o_horario(session: Session, cenario: Cenario):
    agendamento = _agendar(session, cenario)
    agendamento_service.cancelar_com_codigo(
        session, agendamento.id, agendamento.codigo_cancelamento, AGORA_FIXO
    )

    novo = _agendar(session, cenario)

    assert novo.status == StatusAgendamento.AGENDADO


def test_cancelar_com_codigo_errado_levanta_nao_encontrado(session: Session, cenario: Cenario):
    agendamento = _agendar(session, cenario)

    with pytest.raises(RecursoNaoEncontradoError):
        agendamento_service.cancelar_com_codigo(session, agendamento.id, "errado", AGORA_FIXO)

    session.refresh(agendamento)
    assert agendamento.status == StatusAgendamento.AGENDADO


def test_codigo_com_caracteres_nao_ascii_nao_quebra(session: Session, cenario: Cenario):
    agendamento = _agendar(session, cenario)

    with pytest.raises(RecursoNaoEncontradoError):
        agendamento_service.cancelar_com_codigo(session, agendamento.id, "código-ç", AGORA_FIXO)


def test_agendamento_inexistente_tem_a_mesma_resposta_do_codigo_errado(session: Session):
    with pytest.raises(RecursoNaoEncontradoError):
        agendamento_service.cancelar_com_codigo(session, 999, "qualquer", AGORA_FIXO)


def test_agendamento_criado_pela_empresa_nao_cancela_por_codigo(
    session: Session, cenario: Cenario
):
    dados = AgendamentoIn(
        cliente_id=cenario.cliente.id,
        barbeiro_id=cenario.barbeiro.id,
        servico_id=cenario.servico_30.id,
        inicio=na_segunda(10),
    )
    agendamento, _ = agendamento_service.criar(session, dados, AGORA_FIXO)

    with pytest.raises(RecursoNaoEncontradoError):
        agendamento_service.cancelar_com_codigo(session, agendamento.id, "", AGORA_FIXO)


def test_cancelar_duas_vezes_e_idempotente(session: Session, cenario: Cenario):
    agendamento = _agendar(session, cenario)
    codigo = agendamento.codigo_cancelamento
    agendamento_service.cancelar_com_codigo(session, agendamento.id, codigo, AGORA_FIXO)

    repetido = agendamento_service.cancelar_com_codigo(session, agendamento.id, codigo, AGORA_FIXO)

    assert repetido.status == StatusAgendamento.CANCELADO


def test_nao_cancela_horario_que_ja_passou(session: Session, cenario: Cenario):
    agendamento = _agendar(session, cenario)

    with pytest.raises(HorarioPassadoError):
        agendamento_service.cancelar_com_codigo(
            session, agendamento.id, agendamento.codigo_cancelamento, na_segunda(10)
        )

    session.refresh(agendamento)
    assert agendamento.status == StatusAgendamento.AGENDADO


def test_barbeiros_disponiveis_lista_somente_ativos_com_horarios(
    session: Session, cenario: Cenario
):
    inativo = Barbeiro(nome="Inativo", email="inativo@barbearia.com", ativo=False)
    sem_janela = Barbeiro(nome="Sem Janela", email="semjanela@barbearia.com")
    session.add_all([inativo, sem_janela])
    session.commit()

    disponiveis = disponibilidade_service.barbeiros_disponiveis(
        session, cenario.servico_30.id, na_segunda(0).date(), AGORA_FIXO, 15
    )

    assert [barbeiro.nome for barbeiro, _ in disponiveis] == ["João Barbeiro"]
    assert len(disponiveis[0][1]) == 35


def test_barbeiros_disponiveis_vazio_em_dia_sem_janela(session: Session, cenario: Cenario):
    disponiveis = disponibilidade_service.barbeiros_disponiveis(
        session, cenario.servico_30.id, DOMINGO.date(), AGORA_FIXO, 15
    )

    assert disponiveis == []


def test_barbeiros_disponiveis_com_servico_inativo_levanta_erro(
    session: Session, cenario: Cenario
):
    cenario.servico_30.ativo = False
    session.commit()

    with pytest.raises(RecursoInativoError):
        disponibilidade_service.barbeiros_disponiveis(
            session, cenario.servico_30.id, na_segunda(0).date(), AGORA_FIXO, 15
        )
