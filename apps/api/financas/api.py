"""Rotas de perfil financeiro e contas manuais da usuária autenticada."""
import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from django.db import IntegrityError, transaction
from ninja import Field, Router, Schema
from pydantic import BeforeValidator, ConfigDict, StringConstraints, WithJsonSchema

from autenticacao.api import ErroOut
from autenticacao.isolamento import obter_da_usuaria_ou_404
from financas.models import ContaManual, PerfilFinanceiro

perfil_router = Router(tags=["perfil financeiro"])
contas_router = Router(tags=["contas manuais"])

PADRAO_SALDO = r"^-?[0-9]{1,12}(\.[0-9]{1,2})?$"
ESQUEMA_SALDO = {"type": "string", "pattern": PADRAO_SALDO, "examples": ["1500.50"]}
CONTA_DUPLICADA = {"detail": "Já existe uma conta com este nome."}


def validar_saldo(valor: Any) -> Decimal:
    """Aceita somente texto decimal, evitando imprecisão de números JSON."""
    if not isinstance(valor, str) or not re.fullmatch(PADRAO_SALDO[1:-1], valor):
        raise ValueError(
            'Informe o saldo como texto decimal, por exemplo "1500.50", '
            "com até 12 dígitos inteiros e 2 casas decimais."
        )
    # Somar zero transforma "-0.00" em "0.00".
    return Decimal(valor).quantize(Decimal("0.01")) + 0


TextoCurto = Annotated[
    str,
    # Caracteres de controle, como NUL, não podem ser gravados no PostgreSQL.
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]
SaldoEntrada = Annotated[
    Decimal,
    BeforeValidator(validar_saldo),
    WithJsonSchema(ESQUEMA_SALDO),
]
SaldoSaida = Annotated[Decimal, WithJsonSchema(ESQUEMA_SALDO)]


class EntradaEstrita(Schema):
    # Recusa campos como usuaria_id ou moeda em vez de ignorá-los em silêncio.
    model_config = ConfigDict(extra="forbid")


class PerfilIn(EntradaEstrita):
    nome_exibicao: TextoCurto = Field(examples=["Clara Exemplo"])
    previsibilidade_renda: PerfilFinanceiro.PrevisibilidadeRenda = (
        PerfilFinanceiro.PrevisibilidadeRenda.NAO_INFORMADA
    )


class PerfilOut(Schema):
    nome_exibicao: str
    previsibilidade_renda: PerfilFinanceiro.PrevisibilidadeRenda
    criado_em: datetime
    atualizado_em: datetime


class ContaIn(EntradaEstrita):
    nome: TextoCurto = Field(examples=["Conta principal"])
    tipo: ContaManual.Tipo
    saldo_declarado: SaldoEntrada = Field(
        description="Valor informado pela usuária; não é saldo bancário verificado.",
    )


class ContaOut(Schema):
    id: int
    nome: str
    tipo: ContaManual.Tipo
    saldo_declarado: SaldoSaida
    moeda: str
    criado_em: datetime
    atualizado_em: datetime


class ErroValidacaoOut(Schema):
    detail: list[dict[str, Any]]


ERROS_LEITURA = {401: ErroOut}
ERROS_ESCRITA = {401: ErroOut, 403: ErroOut, 422: ErroValidacaoOut}


def salvar_conta(conta: ContaManual) -> bool:
    """Grava a conta e informa se o nome já estava em uso pela usuária."""
    try:
        with transaction.atomic():
            conta.save()
    except IntegrityError:
        return False
    return True


@perfil_router.get("", response={200: PerfilOut, 404: ErroOut, **ERROS_LEITURA})
def consultar_perfil(request):
    """Retorna o perfil da usuária; responde 404 enquanto ele não existir."""
    return obter_da_usuaria_ou_404(PerfilFinanceiro, request.auth)


@perfil_router.put("", response={200: PerfilOut, 201: PerfilOut, **ERROS_ESCRITA})
def salvar_perfil(request, dados: PerfilIn):
    """Cria o perfil (201) ou substitui os dados do perfil existente (200)."""
    perfil, criado = PerfilFinanceiro.objects.update_or_create(
        usuaria=request.auth,
        defaults=dados.model_dump(),
    )
    return 201 if criado else 200, perfil


@contas_router.get("", response={200: list[ContaOut], **ERROS_LEITURA})
def listar_contas(request):
    """Lista somente as contas da usuária autenticada."""
    return ContaManual.objects.da_usuaria(request.auth)


@contas_router.post("", response={201: ContaOut, 409: ErroOut, **ERROS_ESCRITA})
def criar_conta(request, dados: ContaIn):
    """Cria uma conta manual; o nome é único por usuária, sem diferenciar caixa."""
    conta = ContaManual(usuaria=request.auth, **dados.model_dump())
    if not salvar_conta(conta):
        return 409, CONTA_DUPLICADA
    return 201, conta


@contas_router.get(
    "/{conta_id}",
    response={200: ContaOut, 404: ErroOut, **ERROS_LEITURA},
)
def consultar_conta(request, conta_id: int):
    """Retorna uma conta própria; a de outra usuária responde como inexistente."""
    return obter_da_usuaria_ou_404(ContaManual, request.auth, id=conta_id)


@contas_router.put(
    "/{conta_id}",
    response={200: ContaOut, 404: ErroOut, 409: ErroOut, **ERROS_ESCRITA},
)
def editar_conta(request, conta_id: int, dados: ContaIn):
    """Substitui nome, tipo e saldo declarado de uma conta própria."""
    conta = obter_da_usuaria_ou_404(ContaManual, request.auth, id=conta_id)
    for campo, valor in dados.model_dump().items():
        setattr(conta, campo, valor)
    if not salvar_conta(conta):
        return 409, CONTA_DUPLICADA
    return 200, conta
