"""Ferramentas financeiras de leitura disponíveis às telas e aos agentes de IA.

Agentes só escolhem uma ferramenta desta lista e informam parâmetros tipados. A
usuária é entregue pelo backend, a partir da sessão, e nunca faz parte dos parâmetros.
Não existe operação de escrita nem entrada de SQL.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Callable, Literal, Mapping, Optional

from ninja import Field, Schema
from ninja.responses import NinjaJSONEncoder
from pydantic import BeforeValidator, ConfigDict, ValidationError, model_validator

from financas.api import EntradaEstrita, SaldoSaida
from financas.api_reserva import FiltrosReservaIn, ResumoReservaOut
from financas.api_transacoes import DataIso, PeriodoOut, TotalSaida
from financas.consultas import (
    listar_saldos_contas,
    periodo_da_reserva,
    resumir_periodo,
    resumir_reserva,
    totais_por_categoria,
    ultimo_dia_do_mes,
)
from financas.models import ContaManual, TipoLancamento

MAXIMO_DIAS_PERIODO = 731


class ErroFerramenta(Exception):
    """Falha previsível ao executar uma ferramenta, sem dados da usuária."""

    codigo = "erro_ferramenta"


class AcessoNegado(ErroFerramenta):
    codigo = "acesso_negado"


class FerramentaNaoPermitida(ErroFerramenta):
    codigo = "ferramenta_nao_permitida"


class ParametrosInvalidos(ErroFerramenta):
    codigo = "parametros_invalidos"

    def __init__(self, erros: list[dict[str, Any]]):
        super().__init__("Parâmetros inválidos para a ferramenta.")
        self.erros = erros


def recusar_booleano(valor: Any) -> Any:
    if isinstance(valor, bool):
        raise ValueError("Informe um número inteiro.")
    return valor


IdFiltro = Annotated[int, BeforeValidator(recusar_booleano), Field(ge=1)]


class ParametrosPeriodo(EntradaEstrita):
    data_inicio: DataIso
    data_fim: DataIso

    @model_validator(mode="after")
    def conferir_periodo(self):
        if self.data_inicio > self.data_fim:
            raise ValueError("data_inicio não pode ser posterior a data_fim.")
        if (self.data_fim - self.data_inicio).days > MAXIMO_DIAS_PERIODO:
            raise ValueError(f"O período pode ter no máximo {MAXIMO_DIAS_PERIODO} dias.")
        return self


class ParametrosTotais(ParametrosPeriodo):
    tipo: Optional[TipoLancamento] = None
    categoria_id: Optional[IdFiltro] = None


class ParametrosReserva(FiltrosReservaIn):
    model_config = ConfigDict(extra="forbid")


class ParametrosContas(EntradaEstrita):
    pass


class TotalCategoriaOut(Schema):
    categoria_id: int
    categoria_nome: str
    tipo: TipoLancamento
    essencial: bool
    total: TotalSaida
    quantidade: int


# Somas de vários registros usam TotalSaida (até 18 dígitos inteiros), o mesmo
# formato dos totais da listagem de transações: SaldoSaida é o formato de um
# valor individual e limita a 12 dígitos.
class TotaisPorCategoriaOut(Schema):
    receitas: TotalSaida
    despesas: TotalSaida
    resultado: TotalSaida
    quantidade: int
    categorias: list[TotalCategoriaOut]


class ResumoPeriodoOut(Schema):
    receitas: TotalSaida
    despesas: TotalSaida
    despesas_essenciais: TotalSaida
    resultado: TotalSaida
    quantidade: int


class SaldoContaOut(Schema):
    id: int
    nome: str
    tipo: ContaManual.Tipo
    saldo_declarado: SaldoSaida


class SaldosContasOut(Schema):
    total_declarado: TotalSaida
    quantidade: int
    contas: list[SaldoContaOut]


class ResultadoBase(Schema):
    evidencia_id: str = Field(pattern=r"^fin-[0-9a-f]{16}$")
    tipo_evidencia: Literal["financeira"] = "financeira"
    origem: Literal["registros_declarados"] = "registros_declarados"
    moeda: Literal["BRL"] = "BRL"
    periodo: Optional[PeriodoOut]
    parametros: dict[str, Any]


class ResultadoTotaisOut(ResultadoBase):
    ferramenta: Literal["totais_por_categoria"]
    dados: TotaisPorCategoriaOut


class ResultadoResumoOut(ResultadoBase):
    ferramenta: Literal["resumo_periodo"]
    dados: ResumoPeriodoOut


class ResultadoReservaOut(ResultadoBase):
    ferramenta: Literal["consultar_reserva"]
    dados: ResumoReservaOut


class ResultadoContasOut(ResultadoBase):
    ferramenta: Literal["saldos_contas"]
    dados: SaldosContasOut


class FerramentaOut(Schema):
    nome: str
    descricao: str
    rota: str
    parametros: dict[str, Any]


def _periodo_informado(parametros) -> dict[str, date]:
    return {"inicio": parametros.data_inicio, "fim": parametros.data_fim}


def _consultar_totais(usuaria, parametros: ParametrosTotais):
    dados = totais_por_categoria(
        usuaria,
        parametros.data_inicio,
        parametros.data_fim,
        parametros.tipo,
        parametros.categoria_id,
    )
    return _periodo_informado(parametros), dados


def _consultar_resumo(usuaria, parametros: ParametrosPeriodo):
    dados = resumir_periodo(usuaria, parametros.data_inicio, parametros.data_fim)
    return _periodo_informado(parametros), dados


def _consultar_reserva(usuaria, parametros: ParametrosReserva):
    inicio, fim = periodo_da_reserva(parametros.mes_inicio, parametros.mes_fim)
    dados = resumir_reserva(usuaria, parametros.mes_inicio, parametros.mes_fim)
    return {"inicio": inicio, "fim": ultimo_dia_do_mes(fim)}, dados


def _consultar_contas(usuaria, parametros: ParametrosContas):
    return None, listar_saldos_contas(usuaria)


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    rota: str
    parametros: type[Schema]
    resultado: type[ResultadoBase]
    consultar: Callable[[Any, Any], tuple[Optional[dict[str, date]], dict[str, Any]]]


FERRAMENTAS = {
    ferramenta.nome: ferramenta
    for ferramenta in (
        Ferramenta(
            "totais_por_categoria",
            "Soma receitas e despesas declaradas por categoria em um período.",
            "/api/consultas/totais-por-categoria",
            ParametrosTotais,
            ResultadoTotaisOut,
            _consultar_totais,
        ),
        Ferramenta(
            "resumo_periodo",
            "Resume receitas, despesas e despesas essenciais declaradas em um período.",
            "/api/consultas/resumo-periodo",
            ParametrosPeriodo,
            ResultadoResumoOut,
            _consultar_resumo,
        ),
        Ferramenta(
            "consultar_reserva",
            "Retorna meta, saldo declarado, cobertura e progresso da reserva de emergência.",
            "/api/consultas/reserva",
            ParametrosReserva,
            ResultadoReservaOut,
            _consultar_reserva,
        ),
        Ferramenta(
            "saldos_contas",
            "Lista os saldos declarados das contas manuais, sem consultar bancos.",
            "/api/consultas/saldos-contas",
            ParametrosContas,
            ResultadoContasOut,
            _consultar_contas,
        ),
    )
}


def catalogo_ferramentas() -> list[dict[str, Any]]:
    """Descreve as ferramentas permitidas e o schema de seus parâmetros."""
    return [
        {
            "nome": ferramenta.nome,
            "descricao": ferramenta.descricao,
            "rota": ferramenta.rota,
            "parametros": ferramenta.parametros.model_json_schema(),
        }
        for ferramenta in FERRAMENTAS.values()
    ]


def _gerar_evidencia_id(nome: str, parametros: dict, dados: dict) -> str:
    """Gera um ID estável: a mesma consulta com os mesmos dados repete o ID."""
    conteudo = json.dumps(
        {"ferramenta": nome, "parametros": parametros, "dados": dados},
        cls=NinjaJSONEncoder,
        sort_keys=True,
    )
    return "fin-" + hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]


def _exigir_usuaria(usuaria) -> None:
    if not getattr(usuaria, "is_authenticated", False):
        raise AcessoNegado("A ferramenta exige uma usuária autenticada.")


def executar_validado(nome: str, usuaria, parametros: Schema) -> dict[str, Any]:
    """Executa uma ferramenta permitida com parâmetros já validados."""
    _exigir_usuaria(usuaria)
    ferramenta = FERRAMENTAS[nome]
    periodo, dados = ferramenta.consultar(usuaria, parametros)
    publicos = parametros.model_dump(mode="json", exclude_none=True)
    resultado = ferramenta.resultado.model_validate(
        {
            "evidencia_id": _gerar_evidencia_id(nome, publicos, dados),
            "ferramenta": nome,
            "periodo": periodo,
            "parametros": publicos,
            "dados": dados,
        }
    )
    return resultado.model_dump(mode="json")


def executar_ferramenta(
    usuaria,
    nome: str,
    parametros: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Ponto de entrada dos agentes: valida a escolha e os parâmetros antes de consultar."""
    _exigir_usuaria(usuaria)
    ferramenta = FERRAMENTAS.get(nome) if isinstance(nome, str) else None
    if ferramenta is None:
        raise FerramentaNaoPermitida("Ferramenta não permitida.")

    try:
        validados = ferramenta.parametros.model_validate(dict(parametros or {}))
    except (ValidationError, TypeError, ValueError) as erro:
        erros = []
        if isinstance(erro, ValidationError):
            erros = erro.errors(include_url=False, include_context=False, include_input=False)
        raise ParametrosInvalidos(erros) from None
    return executar_validado(nome, usuaria, validados)
