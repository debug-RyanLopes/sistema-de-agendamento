class DominioError(Exception):
    pass


class RecursoNaoEncontradoError(DominioError):
    pass


class ConflitoHorarioError(DominioError):
    pass


class ForaDaDisponibilidadeError(DominioError):
    pass


class HorarioPassadoError(DominioError):
    pass
