"""Dados declarados pela própria usuária, sem qualquer conexão bancária."""
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from autenticacao.isolamento import RegistroDaUsuaria


class PerfilFinanceiro(RegistroDaUsuaria):
    class PrevisibilidadeRenda(models.TextChoices):
        FIXA = "fixa", "Fixa"
        VARIAVEL = "variavel", "Variável"
        MISTA = "mista", "Mista"
        NAO_INFORMADA = "nao_informada", "Não informada"

    nome_exibicao = models.CharField(max_length=80)
    previsibilidade_renda = models.CharField(
        max_length=20,
        choices=PrevisibilidadeRenda.choices,
        default=PrevisibilidadeRenda.NAO_INFORMADA,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["usuaria"], name="perfil_unico_por_usuaria"),
        ]


class ContaManual(RegistroDaUsuaria):
    class Tipo(models.TextChoices):
        CORRENTE = "corrente", "Conta corrente"
        POUPANCA = "poupanca", "Poupança"
        CARTEIRA = "carteira", "Carteira"
        RESERVA = "reserva", "Reserva"
        OUTRA = "outra", "Outra"

    nome = models.CharField(max_length=80)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    # Valor informado pela usuária; não representa saldo bancário verificado.
    saldo_declarado = models.DecimalField(max_digits=14, decimal_places=2)
    moeda = models.CharField(max_length=3, default="BRL", editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                "usuaria",
                Lower("nome"),
                name="conta_nome_unico_por_usuaria",
            ),
        ]


class TipoLancamento(models.TextChoices):
    RECEITA = "receita", "Receita"
    DESPESA = "despesa", "Despesa"


class Categoria(RegistroDaUsuaria):
    nome = models.CharField(max_length=80)
    tipo = models.CharField(max_length=10, choices=TipoLancamento.choices)
    # Identifica as despesas que entram no cálculo da reserva (BE-05).
    essencial = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                "usuaria",
                "tipo",
                Lower("nome"),
                name="categoria_nome_unico_por_usuaria_tipo",
            ),
            models.CheckConstraint(
                condition=Q(essencial=False) | Q(tipo="despesa"),
                name="categoria_essencial_somente_despesa",
            ),
        ]


class Transacao(RegistroDaUsuaria):
    tipo = models.CharField(max_length=10, choices=TipoLancamento.choices)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    moeda = models.CharField(max_length=3, default="BRL", editable=False)
    data = models.DateField()
    descricao = models.CharField(max_length=200, blank=True, default="")
    # RESTRICT impede excluir o vínculo em uso, mas permite remover a usuária.
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.RESTRICT,
        related_name="transacoes",
    )
    conta = models.ForeignKey(
        ContaManual,
        on_delete=models.RESTRICT,
        related_name="transacoes",
        null=True,
        blank=True,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data", "-id"]
        indexes = [
            models.Index(F("usuaria"), F("data").desc(), name="transacao_usuaria_data"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(valor__gt=0), name="transacao_valor_positivo"),
        ]


class ReservaEmergencia(RegistroDaUsuaria):
    saldo_inicial = models.DecimalField(max_digits=14, decimal_places=2)
    meses_cobertura = models.PositiveSmallIntegerField(null=True, blank=True)
    moeda = models.CharField(max_length=3, default="BRL", editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["usuaria"], name="reserva_unica_por_usuaria"),
            models.CheckConstraint(
                condition=Q(saldo_inicial__gte=0),
                name="reserva_saldo_inicial_nao_negativo",
            ),
            models.CheckConstraint(
                condition=Q(meses_cobertura__isnull=True)
                | Q(meses_cobertura__gte=1, meses_cobertura__lte=60),
                name="reserva_meses_cobertura_validos",
            ),
        ]


class TipoMovimentacao(models.TextChoices):
    APORTE = "aporte", "Aporte"
    RETIRADA = "retirada", "Retirada"


class MovimentacaoReserva(RegistroDaUsuaria):
    # O nome próprio evita colisão com ContaManual.Tipo no contrato OpenAPI.
    Tipo = TipoMovimentacao

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    moeda = models.CharField(max_length=3, default="BRL", editable=False)
    data = models.DateField()
    descricao = models.CharField(max_length=200, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-id"]
        indexes = [
            models.Index(F("usuaria"), F("data").desc(), name="movimentacao_usuaria_data"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name="movimentacao_valor_positivo",
            ),
        ]
