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
    MotivoEncerramento,
    ContextoAutorizado,
    EntradaAnalise,
    EntradaComunicacao,
    EntradaPesquisa,
    EntradaValidacao,
    EtapaRastro,
    Papel,
    RespostaFinal,
    SaidaAnalise,
    SaidaComunicacao,
    SaidaPesquisa,
    SaidaValidacao,
)
from .fluxo import (
    MAX_RODADAS_CALCULO,
    MAX_REVISOES_PADRAO,
    ContratoInvalido,
    Etapa,
    Transicao,
    apos_analise,
    apos_pesquisa,
    apos_validacao,
    chamadas_para_calculos,
    falha_de_etapa,
    ler_contrato,
    mesclar_pesquisas,
    montar_resposta,
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
    comunicacao: SaidaComunicacao | None
    revisoes: int
    feedback_validacao: tuple[str, ...]
    rodadas_calculo: int
    calculos_pedidos: tuple[str, ...]
    transicao: Transicao
    # O redutor operator.add faz o LangGraph ACUMULAR as etapas de cada nó.
    etapas: Annotated[tuple[EtapaRastro, ...], operator.add]
    resposta: RespostaFinal


def _executar_agente(papel: Papel, chamada: Callable[[], object], modelo, status_de):
    """Chama o agente, valida a saída e devolve (saida, etapa, transicao_de_falha).

    ``ler_contrato`` revalida a saída a partir de uma cópia: o estado nunca
    guarda o objeto que o agente devolveu, e sim um objeto novo e imutável.
    """
    inicio = time.perf_counter()
    try:
        saida = ler_contrato(modelo, chamada())
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


def _etapas_da_transicao(etapa: EtapaRastro, transicao: Transicao) -> tuple[EtapaRastro, ...]:
    """Etapa do agente + uma etapa do orquestrador quando houve referência quebrada."""
    if not transicao.problemas:
        return (etapa,)
    return (etapa, EtapaRastro(papel=Papel.ORQUESTRADOR, status="inconsistente", duracao_ms=0,
                               codigo="referencia_inexistente"))


def _protegido(papel: Papel, no: Callable[[EstadoFluxo], dict]) -> Callable[[EstadoFluxo], dict]:
    """Nenhuma exceção sai de um nó: erro inesperado vira falha controlada.

    Os agentes já são protegidos em ``_executar_agente``; isto cobre o próprio
    orquestrador (estado inesperado, bug numa transição). Sem esta camada, um
    erro escaparia de ``executar_fluxo`` sem resposta segura.
    """
    def envolvido(estado: EstadoFluxo) -> dict:
        try:
            return no(estado)
        except Exception:  # noqa: BLE001
            etapa = EtapaRastro(papel=Papel.ORQUESTRADOR, status="erro", duracao_ms=0, codigo="erro_interno")
            return {"etapas": (etapa,),
                    "transicao": Transicao(proxima=Etapa.FALHA, motivo=MotivoEncerramento.ERRO_INTERNO)}
    envolvido.__name__ = getattr(no, "__name__", "no")
    return envolvido


def construir_grafo(agentes: Agentes, *, max_revisoes: int = MAX_REVISOES_PADRAO,
                    max_rodadas_calculo: int = MAX_RODADAS_CALCULO):
    # Cada agente recebe CÓPIAS (``.copia()``) do que está no estado. Mesmo que
    # um agente tente alterar a entrada, o estado e as outras etapas não mudam.

    def no_pesquisa(estado: EstadoFluxo) -> dict:
        transicao = estado.get("transicao")
        calculos = transicao.calculos if transicao else ()
        entrada = EntradaPesquisa(contexto=estado["contexto"].copia(), pergunta=estado["pergunta"],
                                  chamadas_solicitadas=chamadas_para_calculos(calculos))
        saida, etapa, falha = _executar_agente(Papel.RESEARCH, lambda: agentes.research(entrada),
                                               SaidaPesquisa, lambda s: s.status)
        if falha:
            return {"etapas": (etapa,), "transicao": falha}
        if not calculos:
            return {"pesquisa": saida, "etapas": (etapa,), "transicao": apos_pesquisa(saida)}
        # Rodada de cálculo: junta com a pesquisa original e volta à Analysis.
        mesclada = mesclar_pesquisas(estado["pesquisa"], saida)
        return {"pesquisa": mesclada, "etapas": (etapa,), "transicao": apos_pesquisa(mesclada),
                "rodadas_calculo": estado.get("rodadas_calculo", 0) + 1,
                "calculos_pedidos": estado.get("calculos_pedidos", ()) + tuple(p.id for p in calculos)}

    def no_analise(estado: EstadoFluxo) -> dict:
        # O feedback fica no estado (não na transição) para sobreviver a uma
        # rodada de cálculo entre a reprovação e a nova análise.
        feedback = estado.get("feedback_validacao", ())
        entrada = EntradaAnalise(contexto=estado["contexto"].copia(), pergunta=estado["pergunta"],
                                 pesquisa=estado["pesquisa"].copia(), feedback_validacao=feedback,
                                 calculos_ja_pedidos=estado.get("calculos_pedidos", ()))
        saida, etapa, falha = _executar_agente(Papel.ANALYSIS, lambda: agentes.analysis(entrada),
                                               SaidaAnalise, lambda s: s.status)
        if falha:
            return {"etapas": (etapa,), "transicao": falha}
        proxima = apos_analise(saida, estado.get("rodadas_calculo", 0), max_rodadas_calculo,
                               estado.get("calculos_pedidos", ()), pesquisa=estado["pesquisa"])
        return {"analise": saida, "etapas": _etapas_da_transicao(etapa, proxima), "transicao": proxima}

    def no_validacao(estado: EstadoFluxo) -> dict:
        entrada = EntradaValidacao(contexto=estado["contexto"].copia(), pergunta=estado["pergunta"],
                                   pesquisa=estado["pesquisa"].copia(), analise=estado["analise"].copia())
        saida, etapa, falha = _executar_agente(Papel.VALIDATION, lambda: agentes.validation(entrada),
                                               SaidaValidacao, lambda s: s.decisao)
        if falha:
            return {"etapas": (etapa,), "transicao": falha}
        revisoes = estado.get("revisoes", 0)
        transicao = apos_validacao(saida, revisoes, max_revisoes, analise=estado["analise"])
        atualizacao = {"validacao": saida, "etapas": _etapas_da_transicao(etapa, transicao),
                       "transicao": transicao, "revisoes": revisoes}
        if transicao.proxima is Etapa.ANALISE:
            atualizacao["revisoes"] = revisoes + 1
            atualizacao["feedback_validacao"] = transicao.feedback
        return atualizacao

    def no_comunicacao(estado: EstadoFluxo) -> dict:
        entrada = EntradaComunicacao(contexto=estado["contexto"].copia(), pergunta=estado["pergunta"],
                                     pesquisa=estado["pesquisa"].copia(), analise=estado["analise"].copia(),
                                     validacao=estado["validacao"].copia())
        saida, etapa, _falha = _executar_agente(Papel.COMMUNICATION, lambda: agentes.communication(entrada),
                                                SaidaComunicacao, lambda s: "ok")
        # O conteúdo já foi aprovado: se a redação falhar, a resposta sai com o
        # texto literal das afirmações aprovadas, em vez de virar falha.
        return {"comunicacao": saida, "etapas": (etapa,), "transicao": Transicao(proxima=Etapa.RESPONDIDA)}

    def no_respondida(estado: EstadoFluxo) -> dict:
        try:
            resposta, problemas = montar_resposta(estado["contexto"], estado["pesquisa"], estado["analise"],
                                                  estado["validacao"], estado.get("comunicacao"), estado["etapas"])
        except Exception:  # noqa: BLE001 - referência quebrada ou erro inesperado
            etapa = EtapaRastro(papel=Papel.ORQUESTRADOR, status="erro", duracao_ms=0,
                                codigo="resposta_inconsistente")
            return {"resposta": resposta_segura(estado["contexto"], Etapa.FALHA,
                                                MotivoEncerramento.CONTRATO_INVALIDO,
                                                tuple(estado["etapas"]) + (etapa,))}
        if problemas:
            etapa = EtapaRastro(papel=Papel.ORQUESTRADOR, status="redacao_literal", duracao_ms=0,
                                codigo="redacao_substituida")
            resposta = resposta.model_copy(update={"etapas": resposta.etapas + (etapa,)})
        return {"resposta": resposta}

    def encerrar(final: Etapa):
        def no(estado: EstadoFluxo) -> dict:
            try:
                lacunas = estado["analise"].lacunas if final is Etapa.PEDIDO_COMPLEMENTO else ()
                return {"resposta": resposta_segura(estado["contexto"], final, estado["transicao"].motivo,
                                                    estado["etapas"], lacunas)}
            except Exception:  # noqa: BLE001 - último recurso: falha genérica
                return {"resposta": resposta_segura(estado["contexto"], Etapa.FALHA,
                                                    MotivoEncerramento.ERRO_INTERNO, estado.get("etapas", ()))}
        return no

    def rota(estado: EstadoFluxo) -> str:
        return estado["transicao"].proxima.value

    grafo = StateGraph(EstadoFluxo)
    grafo.add_node(Etapa.PESQUISA.value, _protegido(Papel.RESEARCH, no_pesquisa))
    grafo.add_node(Etapa.ANALISE.value, _protegido(Papel.ANALYSIS, no_analise))
    grafo.add_node(Etapa.VALIDACAO.value, _protegido(Papel.VALIDATION, no_validacao))
    grafo.add_node(Etapa.COMUNICACAO.value, _protegido(Papel.COMMUNICATION, no_comunicacao))
    grafo.add_node(Etapa.RESPONDIDA.value, no_respondida)
    for final in (Etapa.ABSTENCAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA):
        grafo.add_node(final.value, encerrar(final))

    grafo.add_edge(START, Etapa.PESQUISA.value)
    destinos = {
        Etapa.PESQUISA: [Etapa.ANALISE, Etapa.ABSTENCAO, Etapa.FALHA],
        Etapa.ANALISE: [Etapa.VALIDACAO, Etapa.PESQUISA, Etapa.PEDIDO_COMPLEMENTO, Etapa.ABSTENCAO, Etapa.FALHA],
        Etapa.VALIDACAO: [Etapa.COMUNICACAO, Etapa.ANALISE, Etapa.ABSTENCAO, Etapa.FALHA],
        Etapa.COMUNICACAO: [Etapa.RESPONDIDA],
    }
    for origem, alvos in destinos.items():
        grafo.add_conditional_edges(origem.value, rota, {a.value: a.value for a in alvos})
    for final in (Etapa.RESPONDIDA, Etapa.ABSTENCAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA):
        grafo.add_edge(final.value, END)
    return grafo.compile()


def executar_fluxo(grafo, contexto: ContextoAutorizado, pergunta: str) -> RespostaFinal:
    """Sempre devolve uma ``RespostaFinal`` válida; nunca deixa exceção escapar."""
    try:
        estado = grafo.invoke({"contexto": contexto, "pergunta": pergunta, "revisoes": 0,
                               "feedback_validacao": (), "rodadas_calculo": 0, "calculos_pedidos": (),
                               "etapas": ()})
        return estado["resposta"]
    except Exception:  # noqa: BLE001 - rede de segurança final
        etapa = EtapaRastro(papel=Papel.ORQUESTRADOR, status="erro", duracao_ms=0, codigo="erro_interno")
        return resposta_segura(contexto, Etapa.FALHA, MotivoEncerramento.ERRO_INTERNO, (etapa,))


def diagrama_mermaid() -> str:
    """Diagrama gerado do próprio grafo (com agentes vazios), versionado em contracts/."""
    vazio = lambda entrada: None  # noqa: E731 - só a estrutura importa aqui
    return construir_grafo(Agentes(vazio, vazio, vazio, vazio)).get_graph().draw_mermaid()
