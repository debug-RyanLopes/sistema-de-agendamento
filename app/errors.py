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
