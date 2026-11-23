"""Research Agent: recupera evidências documentais e financeiras (S4-02 / #76).

Implementado como um subgrafo LangGraph de três nós::

    START → planejar → executar → consolidar → END

- **planejar**: um ``Planejador`` (LLM com ``bind_tools`` ou regras) decide
  quais ferramentas chamar, vendo só a pergunta e a data.
- **executar**: invoca cada ferramenta LangChain com o ``ContextoAutorizado``
  em ``RunnableConfig``; as ferramentas checam permissão e devolvem
  evidências tipadas como artefato.
- **consolidar**: deduplica, limita trechos e monta a ``SaidaPesquisa``.

Decisão de segurança: o planejamento acontece **uma vez, antes** da busca. O
resultado das ferramentas nunca volta ao modelo, então um trecho de documento
com "ignore as instruções" não muda o que é consultado. Isso é diferente de
um agente ReAct, que realimenta o modelo a cada passo; aqui não há esse laço
porque a Research não precisa decidir com base no que encontrou.

O agente é chamável (``agente(entrada)``), então entra direto em
``grafo.Agentes(research=agente, ...)``.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
import time
import uuid
from typing import TypedDict

from langchain_core.retrievers import BaseRetriever
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from .contratos import (
    ChamadaFerramenta,
    ContextoAutorizado,
    EntradaPesquisa,
    Permissao,
    RegistroChamada,
    SaidaPesquisa,
    status_da_pesquisa,
)
from .ferramentas import ErroFerramenta, FonteFinanceira, criar_ferramentas, tool_call_de_chamada
from .fluxo import ler_contrato
from .planejador import Planejador, PlanejadorPorRegras, Plano

PERMISSAO_POR_FERRAMENTA = {
    "documentos.buscar": Permissao.DOCUMENTOS_LER,
    "financeiro.consultar": Permissao.FINANCEIRO_LER,
}


class EstadoPesquisa(TypedDict, total=False):
    entrada: EntradaPesquisa
    chamadas: list[ChamadaFerramenta]
    observacoes: list[str]
    registros: list[RegistroChamada]
    evidencias: list
    saida: SaidaPesquisa


class ResearchAgent:
    def __init__(self, retriever: BaseRetriever, fonte: FonteFinanceira, planejador: Planejador | None = None,
                 *, max_trechos: int = 5, relogio=time.perf_counter):
        self.retriever = retriever
        self.fonte = fonte
        self.ferramentas = {f.name: f for f in criar_ferramentas(retriever, fonte, max_trechos=max_trechos)}
        self.planejador = planejador or PlanejadorPorRegras()
        self._relogio = relogio
        self.grafo = self._montar_grafo()

    @property
    def modo(self) -> str:
        sintetico = getattr(self.retriever, "sintetico", False) or self.fonte.sintetico
        return "prototipo_fixtures" if sintetico else "integrado"

    def executar(self, entrada: EntradaPesquisa) -> SaidaPesquisa:
        return self.grafo.invoke({"entrada": entrada})["saida"]

    __call__ = executar

    # ------------------------------------------------------------------
    # Nós do subgrafo
    # ------------------------------------------------------------------

    def _montar_grafo(self):
        grafo = StateGraph(EstadoPesquisa)
        grafo.add_node("planejar", self._planejar)
        grafo.add_node("executar", self._executar)
        grafo.add_node("consolidar", self._consolidar)
        grafo.add_edge(START, "planejar")
        grafo.add_edge("planejar", "executar")
        grafo.add_edge("executar", "consolidar")
        grafo.add_edge("consolidar", END)
        return grafo.compile()

    def _planejar(self, estado: EstadoPesquisa) -> dict:
        entrada = estado["entrada"]
        if entrada.chamadas_solicitadas:
            # Pedido de cálculo da Analysis: executa exatamente o que foi pedido,
            # sem planejador (S4-01, revisão #135). Permissões continuam valendo.
            pedidos = ", ".join(c.pedido_id for c in entrada.chamadas_solicitadas)
            return {"chamadas": list(entrada.chamadas_solicitadas),
                    "observacoes": [f"Cálculos pedidos pela Analysis: {pedidos}."]}
        plano: Plano = self.planejador.planejar(entrada.pergunta, entrada.contexto.data_referencia)
        # Saída do planejador é não confiável: valida tudo. ContratoInvalido sobe
        # para o orquestrador, que registra falha de contrato.
        chamadas = [c if isinstance(c, ChamadaFerramenta) else ler_contrato(ChamadaFerramenta, c)
                    for c in plano.chamadas]
        observacoes = list(plano.observacoes)
        limite = entrada.limites.max_chamadas
        if len(chamadas) > limite:
            observacoes.append(f"Plano limitado a {limite} chamadas.")
            chamadas = chamadas[:limite]
        if not chamadas:
            # O contrato exige ao menos uma chamada: sem plano, tenta o corpus.
            observacoes.append("Planejador não pediu ferramentas; feita busca documental com a pergunta.")
            chamadas = [ChamadaFerramenta(ferramenta="documentos.buscar", consulta=entrada.pergunta[:500])]
        return {"chamadas": chamadas, "observacoes": observacoes}

    def _executar(self, estado: EstadoPesquisa) -> dict:
        contexto = estado["entrada"].contexto
        config = {"configurable": {"contexto": contexto}, "run_name": "research.ferramentas"}
        registros, evidencias = [], {}
        for indice, chamada in enumerate(estado["chamadas"]):
            inicio = self._relogio()
            status, codigo, novas = self._chamar(chamada, indice, contexto, config)
            for evidencia in novas:
                evidencias.setdefault(evidencia.id, evidencia)
            registros.append(RegistroChamada(
                ferramenta=chamada.ferramenta, operacao=chamada.operacao, pedido_id=chamada.pedido_id,
                status=status,
                codigo_erro=codigo, evidencias_ids=[e.id for e in novas],
                duracao_ms=max(0, round((self._relogio() - inicio) * 1000)),
            ))
        return {"registros": registros, "evidencias": list(evidencias.values())}

    def _chamar(self, chamada: ChamadaFerramenta, indice: int, contexto: ContextoAutorizado, config: dict):
        # Checagem antecipada: sem permissão, a ferramenta nem é invocada.
        if PERMISSAO_POR_FERRAMENTA[chamada.ferramenta] not in contexto.permissoes:
            return "negada", "permissao_ausente", []
        tool_call = tool_call_de_chamada(chamada, indice)
        try:
            mensagem = self.ferramentas[tool_call["name"]].invoke(tool_call, config=config)
        except ErroFerramenta as erro:
            status = "negada" if erro.codigo in ("permissao_ausente", "contexto_ausente") else "erro"
            return status, erro.codigo, []
        except (KeyError, TypeError, ValueError, ValidationError):
            return "erro", "resposta_invalida", []
        except Exception:  # noqa: BLE001 - índice fora do ar, conexão perdida...
            return "erro", "ferramenta_indisponivel", []
        novas = list(mensagem.artifact or [])
        if any(e.origem.sintetica and self.modo == "integrado" for e in novas):
            return "erro", "resposta_invalida", []
        return ("ok", None, novas) if novas else ("sem_resultados", None, [])

    def _consolidar(self, estado: EstadoPesquisa) -> dict:
        entrada = estado["entrada"]
        observacoes = list(estado["observacoes"])
        registros, lista = _limitar_trechos(estado["registros"], estado["evidencias"],
                                            entrada.limites.max_trechos, observacoes)
        # Status derivado pela mesma regra que o contrato confere (S4-01).
        status = status_da_pesquisa(bool(lista), registros)
        if any(r.status == "negada" for r in registros):
            observacoes.append("Alguma consulta não foi autorizada para esta requisição.")
        saida = SaidaPesquisa(status=status, modo=self.modo, evidencias=lista, chamadas=registros,
                              observacoes=observacoes)
        return {"saida": saida}


def _limitar_trechos(registros, evidencias, maximo, observacoes):
    """Mantém no máximo ``maximo`` trechos documentais, os de maior score."""
    documentais = sorted((e for e in evidencias if e.tipo == "documental"), key=lambda e: -e.score)
    if len(documentais) <= maximo:
        return registros, evidencias
    cortados = {e.id for e in documentais[maximo:]}
    observacoes.append(f"Mantidos os {maximo} trechos de maior similaridade.")
    ajustados = []
    for r in registros:
        ids = [i for i in r.evidencias_ids if i not in cortados]
        if r.status == "ok" and not ids:
            r = r.model_copy(update={"status": "sem_resultados", "evidencias_ids": ()})
        else:
            r = r.model_copy(update={"evidencias_ids": tuple(ids)})
        ajustados.append(r)
    return ajustados, [e for e in evidencias if e.id not in cortados]


# --------------------------------------------------------------------------
# Demonstração por linha de comando (dados financeiros sempre fictícios)
# --------------------------------------------------------------------------


def main() -> int:
    from .ferramentas import RetrieverChroma, titulos_do_catalogo
    from .fixtures import ConsultaFinanceiraFixture, RetrieverFixture
    from .planejador import PlanejadorLLM, modelo_ollama

    parser = argparse.ArgumentParser(description="Executa o Research Agent com dados fictícios.")
    parser.add_argument("pergunta")
    parser.add_argument("--usuaria", default="usuaria-ficticia-a", help="simula a usuária da sessão")
    parser.add_argument("--data", type=date.fromisoformat, default=date(2026, 11, 18))
    parser.add_argument("--sem-financeiro", action="store_true", help="remove a permissão financeiro:ler")
    parser.add_argument("--planejador", choices=["regras", "ollama"], default="regras")
    parser.add_argument("--modelo", help="modelo do Ollama (padrão: OLLAMA_MODEL ou qwen2.5:7b)")
    parser.add_argument("--chroma-db", type=Path, help="usa o índice real da #67 para documentos")
    parser.add_argument("--colecao")
    args = parser.parse_args()

    if args.chroma_db:
        if not args.colecao:
            parser.error("--colecao é obrigatório com --chroma-db")
        retriever = RetrieverChroma(db_path=args.chroma_db, colecao=args.colecao,
                                    titulos=titulos_do_catalogo(Path("knowledge/catalogo.json")))
    else:
        retriever = RetrieverFixture()
    fonte = ConsultaFinanceiraFixture()
    planejador = None
    if args.planejador == "ollama":
        try:
            planejador = PlanejadorLLM(modelo_ollama(args.modelo), criar_ferramentas(retriever, fonte))
        except ImportError as erro:
            parser.error(str(erro))
    permissoes = [Permissao.DOCUMENTOS_LER] + ([] if args.sem_financeiro else [Permissao.FINANCEIRO_LER])
    contexto = ContextoAutorizado(
        correlation_id=f"demo-{uuid.uuid4().hex[:12]}", usuaria_ref=args.usuaria,
        conversa_id="conv-demo", permissoes=permissoes, data_referencia=args.data,
    )
    saida = ResearchAgent(retriever, fonte, planejador)(EntradaPesquisa(contexto=contexto, pergunta=args.pergunta))
    print(json.dumps(saida.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 1 if saida.status == "falha" else 0


if __name__ == "__main__":
    raise SystemExit(main())
