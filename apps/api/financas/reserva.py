"""Regras determinísticas da reserva de emergência, sem acesso ao banco."""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

DUAS_CASAS = Decimal("0.01")


@dataclass(frozen=True)
class ResultadoReserva:
    estado: str
    faltando: list[str]
    meta: Optional[Decimal]
    progresso_percentual: Optional[Decimal]


def arredondar(valor: Decimal) -> Decimal:
    """Mantém duas casas decimais, arredondando a metade para cima."""
    return valor.quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)


def calcular_media_mensal(total: Decimal, meses_com_registro: int) -> Optional[Decimal]:
    """Calcula a média; sem meses registrados, a informação é insuficiente."""
    if meses_com_registro <= 0:
        return None
    return arredondar(total / meses_com_registro)


def calcular_meta(despesas_mensais: Decimal, meses_cobertura: int) -> Decimal:
    return arredondar(despesas_mensais * meses_cobertura)


def calcular_saldo(saldo_inicial: Decimal, aportes: Decimal, retiradas: Decimal) -> Decimal:
    return saldo_inicial + aportes - retiradas


def calcular_progresso(saldo: Decimal, meta: Decimal) -> Optional[Decimal]:
    """Calcula o percentual somente quando a meta é maior que zero."""
    if meta <= 0:
        return None
    return arredondar(100 * saldo / meta)


def calcular_cobertura(
    saldo: Optional[Decimal],
    despesas_mensais: Optional[Decimal],
) -> Optional[Decimal]:
    """Informa quantos meses de despesas essenciais o saldo declarado cobre."""
    if saldo is None or despesas_mensais is None or despesas_mensais <= 0:
        return None
    return arredondar(saldo / despesas_mensais)


def avaliar_reserva(
    despesas_mensais: Optional[Decimal],
    meses_cobertura: Optional[int],
    saldo: Optional[Decimal],
) -> ResultadoReserva:
    """Combina os dados disponíveis e informa explicitamente o que falta."""
    faltando = []
    if despesas_mensais is None:
        faltando.append("despesas_essenciais")
    if meses_cobertura is None:
        faltando.append("meses_cobertura")
    if saldo is None:
        faltando.append("saldo_inicial")

    meta = None
    if despesas_mensais is not None and meses_cobertura is not None:
        meta = calcular_meta(despesas_mensais, meses_cobertura)

    if faltando:
        return ResultadoReserva("dados_insuficientes", faltando, meta, None)
    if meta <= 0:
        return ResultadoReserva("meta_zero", [], meta, None)
    return ResultadoReserva("calculado", [], meta, calcular_progresso(saldo, meta))


def somar_meses(mes: date, quantidade: int) -> date:
    """Retorna o primeiro dia do mês deslocado pela quantidade informada."""
    total = mes.year * 12 + mes.month - 1 + quantidade
    return date(total // 12, total % 12 + 1, 1)


def contar_meses(inicio: date, fim: date) -> int:
    """Conta os meses do período, incluindo os dois meses informados."""
    return (fim.year - inicio.year) * 12 + fim.month - inicio.month + 1
