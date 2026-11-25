"""Dados declarados pela própria usuária, sem qualquer conexão bancária."""
from django.db import models
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
