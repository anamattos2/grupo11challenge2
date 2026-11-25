"""Rotas da reserva de emergência, calculada com valores declarados no aplicativo."""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Query, Router, Schema
from pydantic import (
    BeforeValidator,
    PlainSerializer,
    StrictInt,
    WithJsonSchema,
    model_validator,
)

from autenticacao.api import ErroOut
from autenticacao.isolamento import obter_da_usuaria_ou_404
from financas.api import (
    ERROS_ESCRITA,
    ERROS_LEITURA,
    EntradaEstrita,
    ErroValidacaoOut,
    SaldoSaida,
)
from financas.api_transacoes import (
    PADRAO_VALOR,
    DataIso,
    Descricao,
    ValorEntrada,
    mesmo_estado_do_banco,
    recusar_filtros_desconhecidos,
)
from financas.consultas import (
    formatar_mes,
    mes_atual,
    resumir_reserva,
    somar_movimentacoes,
)
from financas.models import MovimentacaoReserva, ReservaEmergencia
from financas.reserva import calcular_saldo, contar_meses

reserva_router = Router(tags=["reserva de emergência"])

MAXIMO_MESES_PERIODO = 24
RESERVA_NAO_CONFIGURADA = {"detail": "Configure a reserva antes de registrar movimentações."}
SALDO_INSUFICIENTE = {"detail": "O saldo declarado da reserva é insuficiente para esta operação."}
SALDO_INICIAL_INVALIDO = {
    "detail": "O saldo inicial informado deixaria o saldo declarado da reserva negativo."
}


def validar_saldo_inicial(valor: Any) -> Decimal:
    """Aceita somente texto decimal igual ou maior que zero."""
    if not isinstance(valor, str) or not re.fullmatch(PADRAO_VALOR[1:-1], valor):
        raise ValueError(
            'Informe o saldo inicial como texto decimal, por exemplo "500.00", '
            "com até 12 dígitos inteiros e 2 casas decimais."
        )
    return Decimal(valor).quantize(Decimal("0.01"))


def validar_mes(valor: Any) -> date:
    """Aceita somente meses reais no formato AAAA-MM."""
    if isinstance(valor, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}", valor):
        try:
            return date.fromisoformat(f"{valor}-01")
        except ValueError:
            pass
    raise ValueError("Informe um mês válido no formato AAAA-MM.")


SaldoInicialEntrada = Annotated[
    Decimal,
    BeforeValidator(validar_saldo_inicial),
    WithJsonSchema({"type": "string", "pattern": PADRAO_VALOR, "examples": ["500.00"]}),
]
# Valores calculados podem passar dos 12 dígitos de um valor individual: as
# somas acumulam muitos registros e a meta multiplica a média por até 60 meses.
PADRAO_ACUMULADO = r"^-?[0-9]{1,20}\.[0-9]{2}$"
# O percentual passa de 100 quando o saldo supera a meta; com meta de R$ 0,01 e
# saldo acumulado máximo, chega a 23 dígitos inteiros.
PADRAO_PERCENTUAL = r"^-?[0-9]{1,23}\.[0-9]{2}$"
AcumuladoSaida = Annotated[
    Decimal,
    WithJsonSchema({"type": "string", "pattern": PADRAO_ACUMULADO, "examples": ["1200000000000.00"]}),
]
# Meses que o saldo cobre: saldo ÷ média mensal, com o mesmo alcance do percentual.
CoberturaSaida = Annotated[
    Decimal,
    WithJsonSchema({"type": "string", "pattern": PADRAO_PERCENTUAL, "examples": ["4.50"]}),
]
PercentualSaida = Annotated[
    Decimal,
    WithJsonSchema({"type": "string", "pattern": PADRAO_PERCENTUAL, "examples": ["37.50"]}),
]
MesIso = Annotated[
    date,
    BeforeValidator(validar_mes),
    PlainSerializer(formatar_mes, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}$", "examples": ["2026-08"]}),
]


class ReservaIn(EntradaEstrita):
    saldo_inicial: SaldoInicialEntrada
    meses_cobertura: Optional[Annotated[StrictInt, Field(ge=1, le=60)]] = None


class ReservaOut(Schema):
    saldo_inicial: SaldoSaida
    meses_cobertura: Optional[int]
    moeda: str
    criado_em: datetime
    atualizado_em: datetime


class FiltrosReservaIn(Schema):
    mes_inicio: Optional[MesIso] = None
    mes_fim: Optional[MesIso] = None

    @model_validator(mode="after")
    def conferir_periodo(self):
        if (self.mes_inicio is None) != (self.mes_fim is None):
            raise ValueError("Informe mes_inicio e mes_fim juntos.")
        if self.mes_inicio is None:
            return self
        if self.mes_inicio > self.mes_fim:
            raise ValueError("mes_inicio não pode ser posterior a mes_fim.")
        if self.mes_fim >= mes_atual():
            raise ValueError("O período deve conter somente meses completos.")
        if contar_meses(self.mes_inicio, self.mes_fim) > MAXIMO_MESES_PERIODO:
            raise ValueError(f"O período pode ter no máximo {MAXIMO_MESES_PERIODO} meses.")
        return self


class PeriodoReservaOut(Schema):
    mes_inicio: str
    mes_fim: str
    meses_no_periodo: int
    meses_com_registro: int


class ResumoReservaOut(Schema):
    estado: Literal["calculado", "meta_zero", "dados_insuficientes"]
    faltando: list[Literal["despesas_essenciais", "meses_cobertura", "saldo_inicial"]]
    moeda: str
    periodo: PeriodoReservaOut
    despesas_essenciais_total: AcumuladoSaida
    despesas_essenciais_mensais: Optional[AcumuladoSaida]
    meses_cobertura: Optional[int]
    meses_cobertos: Optional[CoberturaSaida]
    saldo_inicial: Optional[SaldoSaida]
    aportes: AcumuladoSaida
    retiradas: AcumuladoSaida
    saldo_declarado: Optional[AcumuladoSaida]
    meta: Optional[AcumuladoSaida]
    progresso_percentual: Optional[PercentualSaida]


class MovimentacaoIn(EntradaEstrita):
    tipo: MovimentacaoReserva.Tipo
    valor: ValorEntrada
    data: DataIso
    descricao: Descricao = ""

    @model_validator(mode="after")
    def conferir_data(self):
        if self.data > timezone.localdate():
            raise ValueError("A data da movimentação não pode estar no futuro.")
        return self


class MovimentacaoOut(Schema):
    id: int
    tipo: MovimentacaoReserva.Tipo
    valor: SaldoSaida
    moeda: str
    data: date
    descricao: str
    criado_em: datetime


class FiltrosMovimentacaoIn(Schema):
    data_inicio: Optional[DataIso] = None
    data_fim: Optional[DataIso] = None
    tipo: Optional[MovimentacaoReserva.Tipo] = None
    limite: int = Field(default=50, ge=1, le=200)
    deslocamento: int = Field(default=0, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def conferir_periodo(self):
        if self.data_inicio and self.data_fim and self.data_inicio > self.data_fim:
            raise ValueError("data_inicio não pode ser posterior a data_fim.")
        return self


class ListaMovimentacoesOut(Schema):
    moeda: str
    quantidade: int
    limite: int
    deslocamento: int
    itens: list[MovimentacaoOut]


def saldo_com_inicial(usuaria, saldo_inicial: Decimal) -> Decimal:
    totais = somar_movimentacoes(usuaria)
    return calcular_saldo(saldo_inicial, totais["aportes"], totais["retiradas"])


def bloquear_reserva(usuaria) -> Optional[ReservaEmergencia]:
    """Serializa as operações que alteram o saldo declarado da usuária."""
    return ReservaEmergencia.objects.da_usuaria(usuaria).select_for_update().first()


@reserva_router.get(
    "",
    response={200: ResumoReservaOut, 422: ErroValidacaoOut, **ERROS_LEITURA},
)
def consultar_reserva(request, filtros: Query[FiltrosReservaIn]):
    """Calcula meta, saldo e progresso; sem filtros, usa os 3 últimos meses completos."""
    recusar_filtros_desconhecidos(request, FiltrosReservaIn)

    return resumir_reserva(request.auth, filtros.mes_inicio, filtros.mes_fim)


@reserva_router.put(
    "",
    response={200: ReservaOut, 201: ReservaOut, 409: ErroOut, **ERROS_ESCRITA},
)
@transaction.atomic
def salvar_reserva(request, dados: ReservaIn):
    """Cria ou substitui o saldo inicial e os meses de cobertura da reserva."""
    reserva, criada = ReservaEmergencia.objects.select_for_update().get_or_create(
        usuaria=request.auth,
        defaults=dados.model_dump(),
    )
    if criada:
        return 201, reserva

    if saldo_com_inicial(request.auth, dados.saldo_inicial) < 0:
        return 409, SALDO_INICIAL_INVALIDO
    reserva.saldo_inicial = dados.saldo_inicial
    reserva.meses_cobertura = dados.meses_cobertura
    reserva.save()
    return 200, reserva


@reserva_router.get(
    "/movimentacoes",
    response={200: ListaMovimentacoesOut, 422: ErroValidacaoOut, **ERROS_LEITURA},
)
def listar_movimentacoes(request, filtros: Query[FiltrosMovimentacaoIn]):
    """Lista aportes e retiradas próprios, do mais recente para o mais antigo."""
    recusar_filtros_desconhecidos(request, FiltrosMovimentacaoIn)

    movimentacoes = MovimentacaoReserva.objects.da_usuaria(request.auth)
    if filtros.data_inicio:
        movimentacoes = movimentacoes.filter(data__gte=filtros.data_inicio)
    if filtros.data_fim:
        movimentacoes = movimentacoes.filter(data__lte=filtros.data_fim)
    if filtros.tipo:
        movimentacoes = movimentacoes.filter(tipo=filtros.tipo)

    inicio = filtros.deslocamento
    with mesmo_estado_do_banco():
        quantidade = movimentacoes.count()
        itens = list(movimentacoes[inicio : inicio + filtros.limite])
    return {
        "moeda": "BRL",
        "quantidade": quantidade,
        "limite": filtros.limite,
        "deslocamento": inicio,
        "itens": itens,
    }


@reserva_router.post(
    "/movimentacoes",
    response={201: MovimentacaoOut, 409: ErroOut, **ERROS_ESCRITA},
)
@transaction.atomic
def registrar_movimentacao(request, dados: MovimentacaoIn):
    """Registra um aporte ou retirada; o registro já é a confirmação da usuária."""
    reserva = bloquear_reserva(request.auth)
    if reserva is None:
        return 409, RESERVA_NAO_CONFIGURADA

    retirada = dados.tipo == MovimentacaoReserva.Tipo.RETIRADA
    if retirada and dados.valor > saldo_com_inicial(request.auth, reserva.saldo_inicial):
        return 409, SALDO_INSUFICIENTE
    return 201, MovimentacaoReserva.objects.create(usuaria=request.auth, **dados.model_dump())


@reserva_router.get(
    "/movimentacoes/{movimentacao_id}",
    response={200: MovimentacaoOut, 404: ErroOut, **ERROS_LEITURA},
)
def consultar_movimentacao(request, movimentacao_id: int):
    """Retorna uma movimentação própria."""
    return obter_da_usuaria_ou_404(MovimentacaoReserva, request.auth, id=movimentacao_id)


@reserva_router.delete(
    "/movimentacoes/{movimentacao_id}",
    response={204: None, 404: ErroOut, 409: ErroOut, 401: ErroOut, 403: ErroOut},
)
@transaction.atomic
def excluir_movimentacao(request, movimentacao_id: int):
    """Exclui uma movimentação própria, sem deixar o saldo declarado negativo."""
    reserva = bloquear_reserva(request.auth)
    movimentacao = get_object_or_404(
        MovimentacaoReserva.objects.da_usuaria(request.auth),
        id=movimentacao_id,
    )
    if movimentacao.tipo == MovimentacaoReserva.Tipo.APORTE:
        saldo = saldo_com_inicial(request.auth, reserva.saldo_inicial)
        if movimentacao.valor > saldo:
            return 409, SALDO_INSUFICIENTE
    movimentacao.delete()
    return 204, None
