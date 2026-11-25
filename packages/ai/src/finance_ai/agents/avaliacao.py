"""Avaliação offline do Research Agent (S4-02 / #76).

Roda cada caso de ``evaluations/research-agent/casos.json`` pelo agente
completo, com fixtures sintéticas, e mede:

- **seleção exata**: o plano chamou exatamente as operações esperadas (e fez
  ou não busca documental, quando o caso define);
- **precisão e revocação** das ferramentas escolhidas, somando todos os casos;
- **período correto** na consulta ``resumo_transacoes``;
- **status correto**, quando o caso define;
- **violações de isolamento**: evidência financeira com registro de outra
  usuária. Precisa ser zero em qualquer planejador;
- **planos bloqueados**: o contrato recusou o plano (ex.: campo ``usuaria_id``);
  num caso de segurança, isso é um desfecho seguro, não um erro;
- **reserva acionada**: quantas vezes o LLM falhou e as regras assumiram;
- **latência** média por caso.

O objetivo é comparar planejadores (regras × LLM) com os mesmos casos e
registrar uma baseline para detectar regressões.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import json
from pathlib import Path
import statistics
import time
from typing import Callable

from .contratos import ContextoAutorizado, EntradaPesquisa, Permissao, SaidaPesquisa
from .fixtures import PASTA as PASTA_FIXTURES
from .fixtures import ConsultaFinanceiraFixture, RetrieverFixture
from .fluxo import ContratoInvalido
from .planejador import Planejador
from .research import ResearchAgent

DOCS = "documentos"
TODAS = [Permissao.DOCUMENTOS_LER.value, Permissao.FINANCEIRO_LER.value]


@dataclass
class ResultadoCaso:
    id: str
    categoria: str
    ferramentas: list[str] = field(default_factory=list)
    status: str | None = None
    selecao_exata: bool | None = None
    periodo_correto: bool | None = None
    status_correto: bool | None = None
    violacoes_isolamento: int = 0
    plano_bloqueado: bool = False
    reserva_acionada: bool = False
    latencia_ms: int = 0


@dataclass
class Relatorio:
    planejador: str
    casos: int
    selecao_exata: float
    precisao: float
    revocacao: float
    periodo_correto: float
    status_correto: float
    violacoes_isolamento: int
    planos_bloqueados: int
    reserva_acionada: int
    latencia_media_ms: float
    por_caso: list[ResultadoCaso]

    def resumo(self) -> dict:
        dados = asdict(self)
        dados.pop("por_caso")
        return dados


def donos_dos_registros(caminho: Path | None = None) -> dict[str, set[str]]:
    """IDs de transações e contas de cada usuária fictícia."""
    dados = json.loads(Path(caminho or PASTA_FIXTURES / "financeiro.json").read_text(encoding="utf-8"))
    return {
        usuaria: {str(t["id"]) for t in d["transacoes"]} | {str(c["id"]) for c in d["contas"]}
        for usuaria, d in dados["usuarias"].items()
    }


def _ferramentas_do_plano(saida: SaidaPesquisa) -> list[str]:
    nomes = []
    for chamada in saida.chamadas:
        nome = DOCS if chamada.ferramenta == "documentos.buscar" else chamada.operacao.value
        if nome not in nomes:
            nomes.append(nome)
    return nomes


def _periodo_resumo(saida: SaidaPesquisa) -> list[str] | None:
    for evidencia in saida.evidencias:
        if evidencia.tipo == "financeira" and evidencia.origem.operacao.value == "resumo_transacoes":
            loc = evidencia.localizacao
            return [loc.periodo_inicio and loc.periodo_inicio.isoformat(),
                    loc.periodo_fim and loc.periodo_fim.isoformat()]
    return None


def avaliar_caso(agente: ResearchAgent, caso: dict, data_referencia: date,
                 donos: dict[str, set[str]]) -> ResultadoCaso:
    esperado = caso["esperado"]
    contexto = ContextoAutorizado(
        correlation_id=f"aval-{caso['id'].replace('_', '-')}"[:64], usuaria_ref=caso["usuaria"],
        conversa_id="conv-avaliacao", permissoes=caso.get("permissoes", TODAS), data_referencia=data_referencia,
    )
    resultado = ResultadoCaso(id=caso["id"], categoria=caso["categoria"])
    inicio = time.perf_counter()
    try:
        saida = agente.executar(EntradaPesquisa(contexto=contexto, pergunta=caso["pergunta"]))
    except ContratoInvalido:
        resultado.plano_bloqueado = True
        resultado.latencia_ms = round((time.perf_counter() - inicio) * 1000)
        # Plano recusado: nenhuma ferramenta rodou. Pontua seleção como erro,
        # exceto nos casos de segurança, que não pontuam seleção.
        if esperado.get("operacoes") is not None:
            resultado.selecao_exata = False
        return resultado
    resultado.latencia_ms = round((time.perf_counter() - inicio) * 1000)
    resultado.status = saida.status
    resultado.ferramentas = _ferramentas_do_plano(saida)
    resultado.reserva_acionada = any("plano feito por regras" in o for o in saida.observacoes)

    permitidos = donos.get(caso["usuaria"], set())
    for evidencia in saida.evidencias:
        if evidencia.tipo == "financeira":
            resultado.violacoes_isolamento += len(set(evidencia.localizacao.registros) - permitidos)

    if esperado.get("operacoes") is not None:
        operacoes = {f for f in resultado.ferramentas if f != DOCS}
        exato = operacoes == set(esperado["operacoes"])
        if esperado.get("documentos") is not None:
            exato = exato and ((DOCS in resultado.ferramentas) == esperado["documentos"])
        resultado.selecao_exata = exato
    if esperado.get("periodo"):
        resultado.periodo_correto = _periodo_resumo(saida) == esperado["periodo"]
    if esperado.get("status"):
        resultado.status_correto = saida.status == esperado["status"]
    return resultado


def _taxa(valores: list[bool | None]) -> float:
    pontuados = [v for v in valores if v is not None]
    return round(sum(pontuados) / len(pontuados), 3) if pontuados else 0.0


def _precisao_revocacao(casos: list[dict], resultados: list[ResultadoCaso]) -> tuple[float, float]:
    acertos = previstos = esperados = 0
    for caso, r in zip(casos, resultados):
        esp = caso["esperado"]
        if esp.get("operacoes") is None:
            continue
        alvo = set(esp["operacoes"]) | ({DOCS} if esp.get("documentos") else set())
        obtido = set(r.ferramentas)
        if esp.get("documentos") is None:
            obtido.discard(DOCS)
        acertos += len(alvo & obtido)
        previstos += len(obtido)
        esperados += len(alvo)
    precisao = acertos / previstos if previstos else 0.0
    revocacao = acertos / esperados if esperados else 0.0
    return round(precisao, 3), round(revocacao, 3)


def avaliar(casos_json: Path, criar_planejador: Callable[[RetrieverFixture, ConsultaFinanceiraFixture], Planejador | None],
            nome: str) -> Relatorio:
    dados = json.loads(Path(casos_json).read_text(encoding="utf-8"))
    data_referencia = date.fromisoformat(dados["data_referencia"])
    retriever, fonte = RetrieverFixture(), ConsultaFinanceiraFixture()
    agente = ResearchAgent(retriever, fonte, criar_planejador(retriever, fonte))
    donos = donos_dos_registros()
    casos = dados["casos"]
    resultados = [avaliar_caso(agente, caso, data_referencia, donos) for caso in casos]
    precisao, revocacao = _precisao_revocacao(casos, resultados)
    return Relatorio(
        planejador=nome,
        casos=len(casos),
        selecao_exata=_taxa([r.selecao_exata for r in resultados]),
        precisao=precisao,
        revocacao=revocacao,
        periodo_correto=_taxa([r.periodo_correto for r in resultados]),
        status_correto=_taxa([r.status_correto for r in resultados]),
        violacoes_isolamento=sum(r.violacoes_isolamento for r in resultados),
        planos_bloqueados=sum(r.plano_bloqueado for r in resultados),
        reserva_acionada=sum(r.reserva_acionada for r in resultados),
        latencia_media_ms=round(statistics.fmean(r.latencia_ms for r in resultados), 1),
        por_caso=resultados,
    )
