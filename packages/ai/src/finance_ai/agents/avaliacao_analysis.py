"""Avaliação offline do Analysis Agent (S4-03 / #77).

Roda cada caso de ``evaluations/analysis-agent/casos.json`` pela Research com
fixtures e pela Analysis (com a rodada de cálculo, como o orquestrador faz) e
mede:

- **status correto** e **pedido de cálculo correto**;
- **lacunas corretas**: os códigos esperados aparecem;
- **valores corretos**: os trechos esperados (valores do backend já
  formatados) aparecem nas afirmações;
- **afirmações rastreáveis**: fração das afirmações que citam evidências
  existentes e do tipo certo para a natureza;
- **números sem origem**: números do texto que não estão nas evidências
  citadas. Precisa ser zero com qualquer redator (critério "cálculos usam
  ferramenta");
- **rascunhos recusados** e **reserva acionada** (LLM que falhou).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
from pathlib import Path
import statistics
import time

from .analysis import AnalysisAgent, Redator, RedatorLLM
from .contratos import ContextoAutorizado, EntradaAnalise, EntradaPesquisa, Permissao
from .fixtures import ConsultaFinanceiraFixture, RetrieverFixture
from .fluxo import Etapa, apos_pesquisa, chamadas_para_calculos, mesclar_pesquisas
from .redacao import numeros_sem_origem
from .research import ResearchAgent

TODAS = [Permissao.DOCUMENTOS_LER.value, Permissao.FINANCEIRO_LER.value]


@dataclass
class ResultadoCaso:
    id: str
    status: str | None = None
    status_correto: bool = False
    pedido_correto: bool | None = None
    lacunas_corretas: bool | None = None
    valores_corretos: bool | None = None
    afirmacoes: int = 0
    rastreaveis: int = 0
    numeros_sem_origem: list[str] = field(default_factory=list)
    recusas: int = 0
    reserva_acionada: bool = False
    latencia_ms: int = 0


@dataclass
class Relatorio:
    redator: str
    por_caso: list[ResultadoCaso]

    def _taxa(self, campo: str) -> float | None:
        valores = [getattr(r, campo) for r in self.por_caso if getattr(r, campo) is not None]
        return round(sum(valores) / len(valores), 3) if valores else None

    def resumo(self) -> dict:
        total = sum(r.afirmacoes for r in self.por_caso)
        return {
            "redator": self.redator,
            "casos": len(self.por_caso),
            "status_correto": self._taxa("status_correto"),
            "pedido_correto": self._taxa("pedido_correto"),
            "lacunas_corretas": self._taxa("lacunas_corretas"),
            "valores_corretos": self._taxa("valores_corretos"),
            "afirmacoes_rastreaveis": round(sum(r.rastreaveis for r in self.por_caso) / total, 3) if total else None,
            "numeros_sem_origem": sum(len(r.numeros_sem_origem) for r in self.por_caso),
            "rascunhos_recusados": sum(r.recusas for r in self.por_caso),
            "reserva_acionada": sum(r.reserva_acionada for r in self.por_caso),
            "latencia_media_ms": round(statistics.mean(r.latencia_ms for r in self.por_caso), 1),
        }


def _rastreavel(afirmacao, por_id) -> bool:
    if not set(afirmacao.evidencias_ids) <= set(por_id):
        return False
    tipos = {por_id[i].tipo for i in afirmacao.evidencias_ids}
    return tipos == {"documental"} if afirmacao.natureza == "orientacao_educativa" else "financeira" in tipos


def avaliar(caminho: Path, redator: Redator | None = None, nome: str = "regras") -> Relatorio:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    hoje = date.fromisoformat(dados["data_referencia"])
    analysis = AnalysisAgent(redator)
    resultados = []
    for caso in dados["casos"]:
        esperado = caso["esperado"]
        contexto = ContextoAutorizado(correlation_id=f"aval-{caso['id']}"[:64].replace("_", "-"),
                                      usuaria_ref=caso["usuaria"], conversa_id="conv-avaliacao",
                                      permissoes=caso.get("permissoes", TODAS), data_referencia=hoje)
        research = ResearchAgent(RetrieverFixture(), ConsultaFinanceiraFixture(falhar_com=caso.get("falha_fonte")))
        inicio = time.perf_counter()
        resultado = ResultadoCaso(id=caso["id"])
        pesquisa = research(EntradaPesquisa(contexto=contexto, pergunta=caso["pergunta"]))
        if apos_pesquisa(pesquisa).proxima is not Etapa.ANALISE:
            resultado.status = f"pesquisa_{pesquisa.status}"
            resultados.append(resultado)
            continue
        entrada = EntradaAnalise(contexto=contexto, pergunta=caso["pergunta"], pesquisa=pesquisa)
        saida, relatorio = analysis.analisar(entrada)
        pediu = saida.status == "precisa_calculo"
        recusas = len(relatorio.recusas)
        if pediu:
            extra = research(EntradaPesquisa(contexto=contexto, pergunta=caso["pergunta"],
                                             chamadas_solicitadas=chamadas_para_calculos(saida.calculos)))
            entrada = EntradaAnalise(contexto=contexto, pergunta=caso["pergunta"],
                                     pesquisa=mesclar_pesquisas(pesquisa, extra),
                                     calculos_ja_pedidos=[c.id for c in saida.calculos])
            saida, relatorio = analysis.analisar(entrada)
            recusas += len(relatorio.recusas)
        resultado.latencia_ms = round((time.perf_counter() - inicio) * 1000)
        por_id = {e.id: e for e in entrada.pesquisa.evidencias}
        texto = " ".join(a.texto for a in saida.afirmacoes)
        resultado.status = saida.status
        resultado.status_correto = saida.status == esperado["status"]
        if "pede_calculo" in esperado:
            resultado.pedido_correto = pediu == esperado["pede_calculo"]
        if "lacunas" in esperado:
            resultado.lacunas_corretas = set(esperado["lacunas"]) <= {l.codigo for l in saida.lacunas}
        if "contem" in esperado or "nao_contem" in esperado:
            resultado.valores_corretos = (all(t in texto for t in esperado.get("contem", []))
                                          and not any(t in texto for t in esperado.get("nao_contem", [])))
        resultado.afirmacoes = len(saida.afirmacoes)
        resultado.rastreaveis = sum(_rastreavel(a, por_id) for a in saida.afirmacoes)
        resultado.numeros_sem_origem = sorted(n for a in saida.afirmacoes for n in numeros_sem_origem(a, entrada.pesquisa))
        resultado.recusas = recusas
        resultado.reserva_acionada = isinstance(redator, RedatorLLM) and redator.ultimo_motivo_reserva is not None
        resultados.append(resultado)
    return Relatorio(redator=nome, por_caso=resultados)
