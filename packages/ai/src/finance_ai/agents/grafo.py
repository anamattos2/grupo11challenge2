"""Fluxo entre os quatro agentes como grafo LangGraph (S4-01 / #75).

O grafo é a forma executável da política de ``fluxo.py``: cada nó chama um
agente, guarda a saída validada no estado e registra a transição decidida
pelas funções ``apos_*``. As arestas condicionais só leem essa transição.
Assim, a regra de negócio fica em funções puras e testáveis, e o LangGraph
cuida da execução, do estado e da visualização.

Os agentes entram por injeção (``Agentes``). Nesta issue eles são falsos nos
testes; as implementações reais chegam nas issues de cada agente, e timeouts,
persistência e rastros completos ficam para o orquestrador (S4-06 / #80).

Uso::

    grafo = construir_grafo(Agentes(research=..., analysis=..., validation=..., communication=...))
    resposta = executar_fluxo(grafo, contexto, "Quanto gastei em outubro?")
"""

from __future__ import annotations

from dataclasses import dataclass
import operator
import time
from typing import Annotated, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from .contratos import (
    ContextoAutorizado,
    EntradaAnalise,
    EntradaComunicacao,
    EntradaPesquisa,
    EntradaValidacao,
    EtapaRastro,
    Lacuna,
    Papel,
    RespostaFinal,
    SaidaAnalise,
    SaidaComunicacao,
    SaidaPesquisa,
    SaidaValidacao,
)
from .fluxo import (
    MAX_REVISOES_PADRAO,
    ContratoInvalido,
    Etapa,
    Transicao,
    apos_analise,
    apos_comunicacao,
    apos_pesquisa,
    apos_validacao,
    falha_de_etapa,
    ler_contrato,
    resposta_aprovada,
    resposta_segura,
)


@dataclass(frozen=True)
class Agentes:
    """Cada agente é um chamável: recebe a entrada do contrato e devolve a saída.

    Pode ser uma função, um objeto com ``__call__`` ou um ``Runnable`` do
    LangChain adaptado com ``runnable.invoke``.
    """

    research: Callable[[EntradaPesquisa], SaidaPesquisa]
    analysis: Callable[[EntradaAnalise], SaidaAnalise]
    validation: Callable[[EntradaValidacao], SaidaValidacao]
    communication: Callable[[EntradaComunicacao], SaidaComunicacao]


class EstadoFluxo(TypedDict, total=False):
    """Estado compartilhado do grafo. Cada nó devolve só o que mudou."""

    contexto: ContextoAutorizado
    pergunta: str
    pesquisa: SaidaPesquisa
    analise: SaidaAnalise
    validacao: SaidaValidacao
    comunicacao: SaidaComunicacao
    revisoes: int
    transicao: Transicao
    # O redutor operator.add faz o LangGraph ACUMULAR as etapas de cada nó.
    etapas: Annotated[list[EtapaRastro], operator.add]
    resposta: RespostaFinal


def _executar_agente(papel: Papel, chamada: Callable[[], object], modelo, status_de):
    """Chama o agente, valida a saída e devolve (saida, etapa, transicao_de_falha)."""
    inicio = time.perf_counter()
    try:
        saida = chamada()
        saida = ler_contrato(modelo, saida if not isinstance(saida, modelo) else saida.model_dump())
        falha = None
        status, codigo = status_de(saida), None
    except (ContratoInvalido, ValidationError):
        saida, falha = None, falha_de_etapa(papel, contrato=True)
        status, codigo = "erro", "contrato_invalido"
    except TimeoutError:
        saida, falha = None, falha_de_etapa(papel, tempo_esgotado=True)
        status, codigo = "erro", "tempo_esgotado"
    except Exception:  # noqa: BLE001 - qualquer erro de agente vira falha controlada
        saida, falha = None, falha_de_etapa(papel)
        status, codigo = "erro", "excecao"
    etapa = EtapaRastro(papel=papel, status=status, codigo=codigo,
                        duracao_ms=max(0, round((time.perf_counter() - inicio) * 1000)))
    return saida, etapa, falha


def construir_grafo(agentes: Agentes, *, max_revisoes: int = MAX_REVISOES_PADRAO):
    def no_pesquisa(estado: EstadoFluxo) -> dict:
        entrada = EntradaPesquisa(contexto=estado["contexto"], pergunta=estado["pergunta"])
        saida, etapa, falha = _executar_agente(Papel.RESEARCH, lambda: agentes.research(entrada),
                                               SaidaPesquisa, lambda s: s.status)
        if falha:
            return {"etapas": [etapa], "transicao": falha}
        return {"pesquisa": saida, "etapas": [etapa], "transicao": apos_pesquisa(saida)}

    def no_analise(estado: EstadoFluxo) -> dict:
        feedback = estado["transicao"].feedback if estado.get("validacao") else []
        entrada = EntradaAnalise(contexto=estado["contexto"], pergunta=estado["pergunta"],
                                 pesquisa=estado["pesquisa"], feedback_validacao=feedback)
        saida, etapa, falha = _executar_agente(Papel.ANALYSIS, lambda: agentes.analysis(entrada),
                                               SaidaAnalise, lambda s: s.status)
        if falha:
            return {"etapas": [etapa], "transicao": falha}
        return {"analise": saida, "etapas": [etapa], "transicao": apos_analise(saida)}

    def no_validacao(estado: EstadoFluxo) -> dict:
        entrada = EntradaValidacao(contexto=estado["contexto"], pergunta=estado["pergunta"],
                                   pesquisa=estado["pesquisa"], analise=estado["analise"])
        saida, etapa, falha = _executar_agente(Papel.VALIDATION, lambda: agentes.validation(entrada),
                                               SaidaValidacao, lambda s: s.decisao)
        if falha:
            return {"etapas": [etapa], "transicao": falha}
        revisoes = estado.get("revisoes", 0)
        transicao = apos_validacao(saida, revisoes, max_revisoes)
        if transicao.proxima is Etapa.ANALISE:
            revisoes += 1
        return {"validacao": saida, "etapas": [etapa], "transicao": transicao, "revisoes": revisoes}

    def no_comunicacao(estado: EstadoFluxo) -> dict:
        entrada = EntradaComunicacao(contexto=estado["contexto"], pergunta=estado["pergunta"],
                                     pesquisa=estado["pesquisa"], analise=estado["analise"],
                                     validacao=estado["validacao"])
        saida, etapa, falha = _executar_agente(Papel.COMMUNICATION, lambda: agentes.communication(entrada),
                                               SaidaComunicacao, lambda s: "ok")
        if falha:
            return {"etapas": [etapa], "transicao": falha}
        transicao = apos_comunicacao(estado["pesquisa"], estado["analise"], estado["validacao"], saida)
        return {"comunicacao": saida, "etapas": [etapa], "transicao": transicao}

    def no_respondida(estado: EstadoFluxo) -> dict:
        return {"resposta": resposta_aprovada(estado["contexto"], estado["comunicacao"], estado["etapas"])}

    def encerrar(final: Etapa):
        def no(estado: EstadoFluxo) -> dict:
            lacunas: list[Lacuna] = estado["analise"].lacunas if final is Etapa.PEDIDO_COMPLEMENTO else []
            return {"resposta": resposta_segura(estado["contexto"], final, estado["transicao"].motivo,
                                                estado["etapas"], lacunas)}
        return no

    def rota(estado: EstadoFluxo) -> str:
        return estado["transicao"].proxima.value

    grafo = StateGraph(EstadoFluxo)
    grafo.add_node(Etapa.PESQUISA.value, no_pesquisa)
    grafo.add_node(Etapa.ANALISE.value, no_analise)
    grafo.add_node(Etapa.VALIDACAO.value, no_validacao)
    grafo.add_node(Etapa.COMUNICACAO.value, no_comunicacao)
    grafo.add_node(Etapa.RESPONDIDA.value, no_respondida)
    for final in (Etapa.ABSTENCAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA):
        grafo.add_node(final.value, encerrar(final))

    grafo.add_edge(START, Etapa.PESQUISA.value)
    destinos = {
        Etapa.PESQUISA: [Etapa.ANALISE, Etapa.ABSTENCAO, Etapa.FALHA],
        Etapa.ANALISE: [Etapa.VALIDACAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA],
        Etapa.VALIDACAO: [Etapa.COMUNICACAO, Etapa.ANALISE, Etapa.ABSTENCAO, Etapa.FALHA],
        Etapa.COMUNICACAO: [Etapa.RESPONDIDA, Etapa.FALHA],
    }
    for origem, alvos in destinos.items():
        grafo.add_conditional_edges(origem.value, rota, {a.value: a.value for a in alvos})
    for final in (Etapa.RESPONDIDA, Etapa.ABSTENCAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA):
        grafo.add_edge(final.value, END)
    return grafo.compile()


def executar_fluxo(grafo, contexto: ContextoAutorizado, pergunta: str) -> RespostaFinal:
    estado = grafo.invoke({"contexto": contexto, "pergunta": pergunta, "revisoes": 0, "etapas": []})
    return estado["resposta"]


def diagrama_mermaid() -> str:
    """Diagrama gerado do próprio grafo (com agentes vazios), versionado em contracts/."""
    vazio = lambda entrada: None  # noqa: E731 - só a estrutura importa aqui
    return construir_grafo(Agentes(vazio, vazio, vazio, vazio)).get_graph().draw_mermaid()
