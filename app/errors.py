class DominioError(Exception):
    pass


class RecursoNaoEncontradoError(DominioError):
    pass


class RecursoInativoError(DominioError):
    pass


class ConflitoHorarioError(DominioError):
    pass


class ForaDaDisponibilidadeError(DominioError):
    pass


class HorarioPassadoError(DominioError):
    pass


class RecursoDuplicadoError(DominioError):
    pass


class HorarioInvalidoError(DominioError):
    pass


class DataForaDaJanelaError(DominioError):
    pass


class TransicaoInvalidaError(DominioError):
    """O agendamento não está num status que permita a operação pedida."""


class LimiteExcedidoError(DominioError):
    """O cliente já tem o máximo de agendamentos ativos permitido."""


class EstoqueInsuficienteError(DominioError):
    pass


class NaoAutorizadoError(DominioError):
    pass


class AcessoNegadoError(DominioError):
    pass
