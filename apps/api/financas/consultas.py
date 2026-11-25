"""Consultas de leitura sobre os registros declarados por uma usuária.

Toda função recebe a usuária já autenticada e filtra os dados por ela.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from financas.api_transacoes import mesmo_estado_do_banco, somar
from financas.models import (
    ContaManual,
    MovimentacaoReserva,
    ReservaEmergencia,
    TipoLancamento,
    Transacao,
)
from financas.reserva import (
    avaliar_reserva,
    calcular_cobertura,
    calcular_media_mensal,
    calcular_saldo,
    contar_meses,
    somar_meses,
)

MESES_PADRAO = 3


def formatar_mes(mes: date) -> str:
    return f"{mes.year:04d}-{mes.month:02d}"


def mes_atual() -> date:
    return timezone.localdate().replace(day=1)


def periodo_da_reserva(
    mes_inicio: Optional[date],
    mes_fim: Optional[date],
) -> tuple[date, date]:
    """Usa o período informado ou, sem filtros, os 3 últimos meses completos."""
    inicio = mes_inicio or somar_meses(mes_atual(), -MESES_PADRAO)
    fim = mes_fim or somar_meses(mes_atual(), -1)
    return inicio, fim


def ultimo_dia_do_mes(mes: date) -> date:
    return somar_meses(mes, 1) - timedelta(days=1)


def somar_movimentacoes(usuaria) -> dict[str, Decimal]:
    return MovimentacaoReserva.objects.da_usuaria(usuaria).aggregate(
        aportes=somar(MovimentacaoReserva.Tipo.APORTE),
        retiradas=somar(MovimentacaoReserva.Tipo.RETIRADA),
    )


def resumir_reserva(
    usuaria,
    mes_inicio: Optional[date] = None,
    mes_fim: Optional[date] = None,
) -> dict[str, Any]:
    """Calcula meta, saldo declarado, cobertura e progresso da reserva.

    Despesas, configuração e movimentações são lidas no mesmo snapshot do banco
    (``REPEATABLE READ``): um saldo inicial alterado e uma movimentação nova
    não se misturam com o estado anterior no saldo, na cobertura ou no
    progresso. Vale para ``GET /api/reserva`` e para a ferramenta
    ``resumo_reserva``, que usam esta função.
    """
    inicio, fim = periodo_da_reserva(mes_inicio, mes_fim)
    despesas = Transacao.objects.da_usuaria(usuaria).filter(
        tipo=TipoLancamento.DESPESA,
        categoria__essencial=True,
        data__gte=inicio,
        data__lt=somar_meses(fim, 1),
    )
    with mesmo_estado_do_banco():
        resumo = despesas.aggregate(
            total=Sum("valor", default=Decimal("0.00")),
            meses=Count(TruncMonth("data"), distinct=True),
        )
        reserva = ReservaEmergencia.objects.da_usuaria(usuaria).first()
        totais = somar_movimentacoes(usuaria)
    mensais = calcular_media_mensal(resumo["total"], resumo["meses"])
    saldo = None
    if reserva is not None:
        saldo = calcular_saldo(reserva.saldo_inicial, totais["aportes"], totais["retiradas"])
    meses_cobertura = reserva.meses_cobertura if reserva else None
    resultado = avaliar_reserva(mensais, meses_cobertura, saldo)

    return {
        "estado": resultado.estado,
        "faltando": resultado.faltando,
        "moeda": "BRL",
        "periodo": {
            "mes_inicio": formatar_mes(inicio),
            "mes_fim": formatar_mes(fim),
            "meses_no_periodo": contar_meses(inicio, fim),
            "meses_com_registro": resumo["meses"],
        },
        "despesas_essenciais_total": resumo["total"],
        "despesas_essenciais_mensais": mensais,
        "meses_cobertura": meses_cobertura,
        "meses_cobertos": calcular_cobertura(saldo, mensais),
        "saldo_inicial": reserva.saldo_inicial if reserva else None,
        "aportes": totais["aportes"],
        "retiradas": totais["retiradas"],
        "saldo_declarado": saldo,
        "meta": resultado.meta,
        "progresso_percentual": resultado.progresso_percentual,
    }


def _transacoes_do_periodo(usuaria, inicio: date, fim: date):
    return Transacao.objects.da_usuaria(usuaria).filter(data__gte=inicio, data__lte=fim)


def totais_por_categoria(
    usuaria,
    inicio: date,
    fim: date,
    tipo: Optional[TipoLancamento] = None,
    categoria_id: Optional[int] = None,
) -> dict[str, Any]:
    """Soma as transações do período, agrupadas por categoria."""
    transacoes = _transacoes_do_periodo(usuaria, inicio, fim)
    if tipo:
        transacoes = transacoes.filter(tipo=tipo)
    if categoria_id:
        transacoes = transacoes.filter(categoria_id=categoria_id)

    grupos = (
        transacoes.values("categoria_id", "categoria__nome", "categoria__essencial", "tipo")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("tipo", "-total", "categoria_id")
    )
    categorias = [
        {
            "categoria_id": grupo["categoria_id"],
            "categoria_nome": grupo["categoria__nome"],
            "tipo": grupo["tipo"],
            "essencial": grupo["categoria__essencial"],
            "total": grupo["total"],
            "quantidade": grupo["quantidade"],
        }
        for grupo in grupos
    ]
    receitas = sum(
        (c["total"] for c in categorias if c["tipo"] == TipoLancamento.RECEITA),
        Decimal("0.00"),
    )
    despesas = sum(
        (c["total"] for c in categorias if c["tipo"] == TipoLancamento.DESPESA),
        Decimal("0.00"),
    )
    return {
        "receitas": receitas,
        "despesas": despesas,
        "resultado": receitas - despesas,
        "quantidade": sum(c["quantidade"] for c in categorias),
        "categorias": categorias,
    }


def resumir_periodo(usuaria, inicio: date, fim: date) -> dict[str, Any]:
    """Resume receitas e despesas do período, destacando as essenciais."""
    resumo = _transacoes_do_periodo(usuaria, inicio, fim).aggregate(
        receitas=somar(TipoLancamento.RECEITA),
        despesas=somar(TipoLancamento.DESPESA),
        despesas_essenciais=Sum(
            "valor",
            filter=Q(tipo=TipoLancamento.DESPESA, categoria__essencial=True),
            default=Decimal("0.00"),
        ),
        quantidade=Count("id"),
    )
    return {**resumo, "resultado": resumo["receitas"] - resumo["despesas"]}


def listar_saldos_contas(usuaria) -> dict[str, Any]:
    """Lista os saldos declarados das contas manuais da usuária."""
    contas = list(
        ContaManual.objects.da_usuaria(usuaria).values("id", "nome", "tipo", "saldo_declarado")
    )
    return {
        "total_declarado": sum((c["saldo_declarado"] for c in contas), Decimal("0.00")),
        "quantidade": len(contas),
        "contas": contas,
    }
