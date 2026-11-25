"""Contrato da extração de campos de comprovante (S5-02 / #96).

Cada campo diz em que estado está, e as regras abaixo impedem que um campo
"pareça" lido quando não foi:

- ``presente``: há exatamente uma leitura plausível. ``valor`` vem normalizado
  e ``trecho`` é o pedaço do texto lido que o sustenta.
- ``ausente``: nada no texto lido parece com o campo. Sem valor, sem candidatos.
- ``ambiguo``: há leitura, mas não dá para escolher com segurança (dois totais
  diferentes, valor sem rótulo de total, leitura com baixa confiança). **Sem
  valor escolhido**: as opções vão em ``candidatos``, para a usuária decidir.

Nada aqui é despesa: a extração só alimenta a prévia editável (RF17).
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field, model_validator

EstadoCampo = Literal["presente", "ausente", "ambiguo"]
StatusExtracao = Literal["completa", "parcial", "ilegivel"]


class Campo(Schema):
    estado: EstadoCampo
    valor: str | None = Field(default=None, max_length=120,
                              description="Normalizado: '19.40', '2026-10-03' ou o nome lido.")
    trecho: str | None = Field(default=None, max_length=200, description="Texto lido que sustenta o valor.")
    candidatos: list[str] = Field(default_factory=list, max_length=5)
    motivo: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _coerente(self):
        if self.estado == "presente":
            if not self.valor or not self.trecho or self.candidatos:
                raise ValueError("campo presente exige valor e trecho, e nenhum candidato")
        elif self.estado == "ausente":
            if self.valor or self.trecho or self.candidatos:
                raise ValueError("campo ausente não tem valor, trecho nem candidatos")
        elif self.valor:
            raise ValueError("campo ambíguo nunca escolhe um valor")
        elif not (self.candidatos or self.motivo):
            raise ValueError("campo ambíguo explica o motivo ou lista os candidatos")
        return self


class CamposExtraidos(Schema):
    valor_total: Campo
    data: Campo
    estabelecimento: Campo

    @model_validator(mode="after")
    def _formatos(self):
        if self.valor_total.estado == "presente":
            try:
                if Decimal(self.valor_total.valor) <= 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise ValueError("valor_total presente deve ser um decimal positivo") from None
        if self.data.estado == "presente":
            date.fromisoformat(self.data.valor)
        return self


class ExtracaoOut(Schema):
    comprovante_id: UUID
    status: StatusExtracao
    campos: CamposExtraidos
    motor: str
    avisos: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _status_coerente(self):
        estados = [self.campos.valor_total.estado, self.campos.data.estado, self.campos.estabelecimento.estado]
        if self.status == "completa" and estados != ["presente"] * 3:
            raise ValueError("extração completa exige os três campos presentes")
        if self.status == "ilegivel" and any(e != "ausente" for e in estados):
            raise ValueError("imagem ilegível não tem campo lido")
        return self
