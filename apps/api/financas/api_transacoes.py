"""Rotas de categorias, receitas e despesas declaradas pela usuária."""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Optional

from django.db import transaction
from django.db.models import Case, Count, DecimalField, Q, RestrictedError, Sum, Value, When, Window
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, Query, Router, Schema
from ninja.errors import ValidationError
from pydantic import BeforeValidator, StrictBool, StrictInt, StringConstraints
from pydantic import WithJsonSchema, model_validator

from autenticacao.api import ErroOut
from autenticacao.isolamento import obter_da_usuaria_ou_404
from financas.api import (
    ERROS_ESCRITA,
    ERROS_LEITURA,
    EntradaEstrita,
    ErroValidacaoOut,
    SaldoSaida,
    TextoCurto,
    salvar_com_nome_unico,
)
from financas.models import Categoria, ContaManual, TipoLancamento, Transacao

categorias_router = Router(tags=["categorias"])
transacoes_router = Router(tags=["transações"])

PADRAO_VALOR = r"^[0-9]{1,12}(\.[0-9]{1,2})?$"
# Os totais somam valores de até 12 dígitos inteiros, então precisam de mais
# espaço que um valor individual: até 18 dígitos inteiros (DecimalField 20,2).
DIGITOS_TOTAL = 20
PADRAO_TOTAL = r"^-?[0-9]{1,18}\.[0-9]{2}$"
RESTRICAO_CATEGORIA_UNICA = "categoria_nome_unico_por_usuaria_tipo"
CATEGORIA_DUPLICADA = {"detail": "Já existe uma categoria deste tipo com este nome."}
CATEGORIA_EM_USO = {"detail": "Esta categoria possui transações vinculadas."}


def validar_valor(valor: Any) -> Decimal:
    """Aceita somente texto decimal positivo, sem imprecisão de números JSON."""
    if not isinstance(valor, str) or not re.fullmatch(PADRAO_VALOR[1:-1], valor):
        raise ValueError(
            'Informe o valor como texto decimal, por exemplo "89.90", '
            "com até 12 dígitos inteiros e 2 casas decimais."
        )
    decimal = Decimal(valor).quantize(Decimal("0.01"))
    if decimal <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    return decimal


def validar_data(valor: Any) -> date:
    """Aceita somente datas reais no formato AAAA-MM-DD."""
    if isinstance(valor, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise ValueError("Informe uma data válida no formato AAAA-MM-DD.")


ValorEntrada = Annotated[
    Decimal,
    BeforeValidator(validar_valor),
    WithJsonSchema({"type": "string", "pattern": PADRAO_VALOR, "examples": ["89.90"]}),
]
DataIso = Annotated[
    date,
    BeforeValidator(validar_data),
    WithJsonSchema({"type": "string", "format": "date", "examples": ["2026-11-10"]}),
]
Descricao = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=200,
        pattern=r"^[^\x00-\x1f\x7f]*$",
    ),
]
IdRegistro = Annotated[StrictInt, Field(ge=1)]


class CategoriaIn(EntradaEstrita):
    nome: TextoCurto = Field(examples=["Alimentação"])
    tipo: TipoLancamento
    essencial: StrictBool = False

    @model_validator(mode="after")
    def conferir_essencial(self):
        if self.essencial and self.tipo != TipoLancamento.DESPESA:
            raise ValueError("Somente categorias de despesa podem ser essenciais.")
        return self


class CategoriaOut(Schema):
    id: int
    nome: str
    tipo: TipoLancamento
    essencial: bool
    criado_em: datetime
    atualizado_em: datetime


class TransacaoIn(EntradaEstrita):
    tipo: TipoLancamento
    valor: ValorEntrada
    data: DataIso
    categoria_id: IdRegistro
    conta_id: Optional[IdRegistro] = None
    descricao: Descricao = ""

    @model_validator(mode="after")
    def conferir_data(self):
        if self.data > timezone.localdate():
            raise ValueError("A data da transação não pode estar no futuro.")
        return self


class TransacaoOut(Schema):
    id: int
    tipo: TipoLancamento
    valor: SaldoSaida
    moeda: str
    data: date
    descricao: str
    categoria_id: int
    categoria_nome: str = Field(alias="categoria.nome")
    conta_id: Optional[int]
    criado_em: datetime
    atualizado_em: datetime


class FiltrosIn(Schema):
    data_inicio: Optional[DataIso] = None
    data_fim: Optional[DataIso] = None
    categoria_id: Optional[int] = Field(default=None, ge=1)
    tipo: Optional[TipoLancamento] = None
    limite: int = Field(default=50, ge=1, le=200)
    deslocamento: int = Field(default=0, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def conferir_periodo(self):
        if self.data_inicio and self.data_fim and self.data_inicio > self.data_fim:
            raise ValueError("data_inicio não pode ser posterior a data_fim.")
        return self


class PeriodoOut(Schema):
    inicio: Optional[date]
    fim: Optional[date]


TotalSaida = Annotated[
    Decimal,
    WithJsonSchema({"type": "string", "pattern": PADRAO_TOTAL, "examples": ["1250.40"]}),
]


class TotaisOut(Schema):
    receitas: TotalSaida
    despesas: TotalSaida
    resultado: TotalSaida


class ListaTransacoesOut(Schema):
    periodo: PeriodoOut
    moeda: str
    totais: TotaisOut
    quantidade: int
    limite: int
    deslocamento: int
    itens: list[TransacaoOut]


def referencia_invalida(campo: str, mensagem: str) -> ValidationError:
    return ValidationError(
        [{"type": "referencia_invalida", "loc": ["body", "dados", campo], "msg": mensagem}]
    )


def bloquear_da_usuaria_ou_404(modelo, usuaria, registro_id: int):
    """Trava o registro próprio até o fim da transação do banco."""
    registros = modelo.objects.da_usuaria(usuaria).select_for_update()
    return get_object_or_404(registros, id=registro_id)


def preencher_transacao(registro: Transacao, usuaria, dados: TransacaoIn) -> Transacao:
    """Copia os dados, aceitando somente categoria e conta da própria usuária."""
    categoria = (
        Categoria.objects.da_usuaria(usuaria)
        .select_for_update()
        .filter(id=dados.categoria_id)
        .first()
    )
    if categoria is None:
        raise referencia_invalida("categoria_id", "Categoria não encontrada.")
    if categoria.tipo != dados.tipo:
        raise referencia_invalida(
            "categoria_id", "A categoria não corresponde ao tipo da transação."
        )

    conta = None
    if dados.conta_id is not None:
        conta = ContaManual.objects.da_usuaria(usuaria).filter(id=dados.conta_id).first()
        if conta is None:
            raise referencia_invalida("conta_id", "Conta não encontrada.")

    registro.tipo = dados.tipo
    registro.valor = dados.valor
    registro.data = dados.data
    registro.descricao = dados.descricao
    registro.categoria = categoria
    registro.conta = conta
    registro.save()
    return registro


CAMPO_TOTAL = DecimalField(max_digits=DIGITOS_TOTAL, decimal_places=2)


def somar(tipo: TipoLancamento):
    return Coalesce(
        Sum("valor", filter=Q(tipo=tipo)),
        Value(Decimal("0.00")),
        output_field=CAMPO_TOTAL,
    )


def somar_na_janela(tipo: TipoLancamento) -> Window:
    """Soma de ``tipo`` sobre todo o filtro, repetida em cada linha da página.

    A janela sem partição nem ordenação cobre todas as linhas filtradas, e o
    PostgreSQL a calcula antes do LIMIT/OFFSET.
    """
    valor_do_tipo = Case(When(tipo=tipo, then="valor"), default=Value(Decimal("0.00")),
                         output_field=CAMPO_TOTAL)
    return Window(Sum(valor_do_tipo, output_field=CAMPO_TOTAL), output_field=CAMPO_TOTAL)


@categorias_router.get("", response={200: list[CategoriaOut], **ERROS_LEITURA})
def listar_categorias(request):
    """Lista somente as categorias da usuária autenticada."""
    return Categoria.objects.da_usuaria(request.auth)


@categorias_router.post("", response={201: CategoriaOut, 409: ErroOut, **ERROS_ESCRITA})
def criar_categoria(request, dados: CategoriaIn):
    """Cria uma categoria; o nome é único por usuária e tipo."""
    categoria = Categoria(usuaria=request.auth, **dados.model_dump())
    if not salvar_com_nome_unico(categoria, RESTRICAO_CATEGORIA_UNICA):
        return 409, CATEGORIA_DUPLICADA
    return 201, categoria


@categorias_router.get(
    "/{categoria_id}",
    response={200: CategoriaOut, 404: ErroOut, **ERROS_LEITURA},
)
def consultar_categoria(request, categoria_id: int):
    """Retorna uma categoria própria."""
    return obter_da_usuaria_ou_404(Categoria, request.auth, id=categoria_id)


@categorias_router.put(
    "/{categoria_id}",
    response={200: CategoriaOut, 404: ErroOut, 409: ErroOut, **ERROS_ESCRITA},
)
@transaction.atomic
def editar_categoria(request, categoria_id: int, dados: CategoriaIn):
    """Substitui os dados; o tipo só muda se não houver transações vinculadas."""
    categoria = bloquear_da_usuaria_ou_404(Categoria, request.auth, categoria_id)
    if dados.tipo != categoria.tipo and categoria.transacoes.exists():
        return 409, CATEGORIA_EM_USO
    for campo, valor in dados.model_dump().items():
        setattr(categoria, campo, valor)
    if not salvar_com_nome_unico(categoria, RESTRICAO_CATEGORIA_UNICA):
        return 409, CATEGORIA_DUPLICADA
    return 200, categoria


@categorias_router.delete(
    "/{categoria_id}",
    response={204: None, 404: ErroOut, 409: ErroOut, 401: ErroOut, 403: ErroOut},
)
@transaction.atomic
def excluir_categoria(request, categoria_id: int):
    """Exclui uma categoria própria que não possua transações."""
    categoria = bloquear_da_usuaria_ou_404(Categoria, request.auth, categoria_id)
    try:
        categoria.delete()
    except RestrictedError:
        return 409, CATEGORIA_EM_USO
    return 204, None


@transacoes_router.get(
    "",
    response={200: ListaTransacoesOut, 422: ErroValidacaoOut, **ERROS_LEITURA},
)
def listar_transacoes(request, filtros: Query[FiltrosIn]):
    """Lista as transações próprias; os totais consideram todo o filtro aplicado."""
    # Um filtro digitado errado não pode devolver totais de todo o histórico.
    desconhecidos = sorted(set(request.GET) - set(FiltrosIn.model_fields))
    if desconhecidos:
        raise ValidationError(
            [
                {
                    "type": "filtro_desconhecido",
                    "loc": ["query", nome],
                    "msg": "Filtro desconhecido.",
                }
                for nome in desconhecidos
            ]
        )

    transacoes = Transacao.objects.da_usuaria(request.auth)
    if filtros.data_inicio:
        transacoes = transacoes.filter(data__gte=filtros.data_inicio)
    if filtros.data_fim:
        transacoes = transacoes.filter(data__lte=filtros.data_fim)
    if filtros.categoria_id:
        transacoes = transacoes.filter(categoria_id=filtros.categoria_id)
    if filtros.tipo:
        transacoes = transacoes.filter(tipo=filtros.tipo)

    # Itens, totais e quantidade saem da mesma consulta, logo do mesmo estado do
    # banco: uma escrita concorrente não pode deixar a página e os totais
    # incompatíveis. Só uma página vazia precisa da consulta de agregação.
    inicio = filtros.deslocamento
    itens = list(
        transacoes.select_related("categoria").annotate(
            _total_receitas=somar_na_janela(TipoLancamento.RECEITA),
            _total_despesas=somar_na_janela(TipoLancamento.DESPESA),
            _quantidade=Window(Count("id")),
        )[inicio : inicio + filtros.limite]
    )
    if itens:
        primeiro = itens[0]
        resumo = {
            "receitas": primeiro._total_receitas,
            "despesas": primeiro._total_despesas,
            "quantidade": primeiro._quantidade,
        }
    else:
        resumo = transacoes.aggregate(
            receitas=somar(TipoLancamento.RECEITA),
            despesas=somar(TipoLancamento.DESPESA),
            quantidade=Count("id"),
        )
    return {
        "periodo": {"inicio": filtros.data_inicio, "fim": filtros.data_fim},
        "moeda": "BRL",
        "totais": {
            "receitas": resumo["receitas"],
            "despesas": resumo["despesas"],
            "resultado": resumo["receitas"] - resumo["despesas"],
        },
        "quantidade": resumo["quantidade"],
        "limite": filtros.limite,
        "deslocamento": inicio,
        "itens": itens,
    }


@transacoes_router.post("", response={201: TransacaoOut, **ERROS_ESCRITA})
@transaction.atomic
def criar_transacao(request, dados: TransacaoIn):
    """Registra uma receita ou despesa declarada pela usuária."""
    return 201, preencher_transacao(Transacao(usuaria=request.auth), request.auth, dados)


@transacoes_router.get(
    "/{transacao_id}",
    response={200: TransacaoOut, 404: ErroOut, **ERROS_LEITURA},
)
def consultar_transacao(request, transacao_id: int):
    """Retorna uma transação própria."""
    return get_object_or_404(
        Transacao.objects.da_usuaria(request.auth).select_related("categoria"),
        id=transacao_id,
    )


@transacoes_router.put(
    "/{transacao_id}",
    response={200: TransacaoOut, 404: ErroOut, **ERROS_ESCRITA},
)
@transaction.atomic
def editar_transacao(request, transacao_id: int, dados: TransacaoIn):
    """Substitui todos os dados de uma transação própria."""
    registro = bloquear_da_usuaria_ou_404(Transacao, request.auth, transacao_id)
    return 200, preencher_transacao(registro, request.auth, dados)


@transacoes_router.delete(
    "/{transacao_id}",
    response={204: None, 404: ErroOut, 401: ErroOut, 403: ErroOut},
)
@transaction.atomic
def excluir_transacao(request, transacao_id: int):
    """Exclui uma transação própria."""
    bloquear_da_usuaria_ou_404(Transacao, request.auth, transacao_id).delete()
    return 204, None
