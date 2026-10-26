from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import iniciar_escrita
from app.errors import EstoqueInsuficienteError
from app.models import CENTAVOS, Produto, Venda, VendaItem
from app.schemas import VendaIn, VendaItemOut, VendaOut
from app.services import cadastro_service


def _saida(venda: Venda, itens: list[VendaItem]) -> VendaOut:
    return VendaOut(
        id=venda.id,
        criado_em=venda.criado_em,
        total=venda.total,
        observacao=venda.observacao,
        itens=[VendaItemOut.model_validate(item) for item in itens],
    )


def registrar(session: Session, dados: VendaIn, agora: datetime) -> VendaOut:
    """Baixa o estoque e grava a venda na mesma transação; item sem estoque cancela tudo."""
    iniciar_escrita(session)
    itens: list[VendaItem] = []
    total = Decimal("0")
    for pedido in dados.itens:
        produto = cadastro_service.obter_ativo(session, Produto, pedido.produto_id, "produto")
        if produto.estoque < pedido.quantidade:
            raise EstoqueInsuficienteError(
                f"estoque insuficiente de {produto.nome}: há {produto.estoque}, "
                f"pedido {pedido.quantidade}"
            )
        produto.estoque -= pedido.quantidade
        itens.append(
            VendaItem(
                produto_id=produto.id, quantidade=pedido.quantidade, preco_unitario=produto.preco
            )
        )
        total += produto.preco * pedido.quantidade
    venda = Venda(criado_em=agora, total=total.quantize(CENTAVOS), observacao=dados.observacao)
    session.add(venda)
    session.flush()
    for item in itens:
        item.venda_id = venda.id
    session.add_all(itens)
    session.commit()
    return _saida(venda, itens)


def listar(session: Session, desde: datetime | None = None, limite: int = 100) -> list[VendaOut]:
    consulta = select(Venda).order_by(Venda.criado_em.desc(), Venda.id.desc()).limit(limite)
    if desde is not None:
        consulta = consulta.where(Venda.criado_em >= desde)
    vendas = list(session.scalars(consulta))
    if not vendas:
        return []
    itens = session.scalars(
        select(VendaItem).where(VendaItem.venda_id.in_([venda.id for venda in vendas]))
    )
    por_venda: dict[int, list[VendaItem]] = {venda.id: [] for venda in vendas}
    for item in itens:
        por_venda[item.venda_id].append(item)
    return [_saida(venda, por_venda[venda.id]) for venda in vendas]


def receita(session: Session, desde: datetime, ate: datetime) -> Decimal:
    from sqlalchemy import func

    valor = session.scalar(
        select(func.coalesce(func.sum(Venda.total), 0)).where(
            Venda.criado_em >= desde, Venda.criado_em < ate
        )
    )
    return Decimal(str(valor or 0)).quantize(CENTAVOS)
