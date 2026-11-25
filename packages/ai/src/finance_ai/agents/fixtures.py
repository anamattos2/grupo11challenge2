"""Ferramentas com dados sintéticos para o protótipo do Research Agent (S4-02 / #76).

**Protótipo.** Estas classes existem para desenvolver e testar o agente antes
da integração real. Elas se identificam com ``sintetico = True``, e toda
evidência produzida sai com ``origem.sintetica = true``. O Research Agent, ao
usá-las, marca a saída com ``modo = "prototipo_fixtures"``.

- ``RetrieverFixture`` é um ``BaseRetriever`` do LangChain com os metadados do
  contrato v1 da recuperação documental (#67), mas pontua por sobreposição de
  palavras, não por embeddings.
- ``ConsultaFinanceiraFixture`` imita as regras do backend: filtra pela
  usuária do contexto e trata dados de outra usuária como inexistentes.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from .contratos import (
    ContextoAutorizado,
    EvidenciaFinanceira,
    LocalizacaoFinanceira,
    OperacaoFinanceira,
    OrigemFinanceira,
    ParametrosFinanceiros,
)
from .backend import ROTAS, resumo_reserva, traduzir
from .contratos import _congelar
from .ferramentas import ErroFerramenta, documento_de_trecho_v1, id_financeiro

PASTA = Path(__file__).with_name("fixtures")
CENTAVO = Decimal("0.01")

_STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no",
    "na", "nos", "nas", "por", "para", "com", "sem", "e", "ou", "que", "se", "eu", "meu", "minha",
    "meus", "minhas", "voce", "quanto", "quanta", "qual", "quais", "como", "devo", "ter", "tenho",
    "ser", "sao", "e", "mais", "menos", "ao", "aos", "isso", "esse", "essa", "este", "esta", "mes",
}


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.lower())
    return "".join(ch for ch in sem_acento if unicodedata.category(ch) != "Mn")


def _termos(texto: str) -> set[str]:
    termos = set()
    for palavra in re.findall(r"\w+", normalizar(texto)):
        if palavra in _STOPWORDS or len(palavra) < 2:
            continue
        termos.add(palavra[:-1] if len(palavra) > 4 and palavra.endswith("s") else palavra)
    return termos


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _dinheiro(valor: Decimal) -> str:
    return format(valor.quantize(CENTAVO), "f")


class RetrieverFixture(BaseRetriever):
    """``BaseRetriever`` lexical sobre ``fixtures/documentos.json``.

    Devolve ``Document`` com os mesmos metadados do contrato v1 da #67, então
    o restante do agente não distingue esta fixture do retriever real.
    """

    caminho: Path | None = None
    min_score: float = 0.25
    k: int = 5
    falhar_com: str | None = None
    sintetico: bool = True
    titulos: dict[str, str] = Field(default_factory=dict)
    trechos: list[dict] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        dados = json.loads(Path(self.caminho or PASTA / "documentos.json").read_text(encoding="utf-8"))
        for doc in dados["documentos"]:
            self.titulos[doc["document_id"]] = doc["titulo"]
            fonte_sha = _sha(json.dumps(doc, ensure_ascii=False, sort_keys=True))
            for numero, texto in enumerate(doc["paginas"], start=1):
                identidade = json.dumps([doc["document_id"], fonte_sha, numero, 0, len(texto), texto],
                                        ensure_ascii=False)
                self.trechos.append({
                    "chunk_id": _sha(identidade), "document_id": doc["document_id"],
                    "source_sha256": fonte_sha, "page_number": numero,
                    "start": 0, "end": len(texto), "text": texto,
                })

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        if self.falhar_com:
            raise ErroFerramenta(self.falhar_com)
        termos = _termos(query)
        if not termos:
            return []
        pontuados = []
        for trecho in self.trechos:
            score = len(termos & _termos(trecho["text"])) / len(termos)
            if score >= self.min_score:
                pontuados.append({**trecho, "score": round(score, 4)})
        pontuados.sort(key=lambda t: (-t["score"], t["document_id"], t["page_number"]))
        return [documento_de_trecho_v1(item, titulos=self.titulos, sintetica=True) for item in pontuados[: self.k]]


class ConsultaFinanceiraFixture:
    """``FonteFinanceira`` sobre ``fixtures/financeiro.json``."""

    sintetico = True

    # Mesma tradução operação → ferramenta da BE-06 usada pelo adaptador real,
    # para que a fixture e a integração produzam evidências equivalentes.

    def __init__(self, caminho: Path | None = None, *, falhar_com: str | None = None):
        dados = json.loads(Path(caminho or PASTA / "financeiro.json").read_text(encoding="utf-8"))
        self._usuarias = dados["usuarias"]
        self.falhar_com = falhar_com
        self.consultas_recebidas: list[str] = []  # usado nos testes de isolamento

    def consultar(self, contexto: ContextoAutorizado, operacao: OperacaoFinanceira,
                  parametros: ParametrosFinanceiros) -> EvidenciaFinanceira | None:
        operacao = OperacaoFinanceira(operacao)
        self.consultas_recebidas.append(contexto.usuaria_ref)
        if self.falhar_com:
            raise ErroFerramenta(self.falhar_com)
        dados = self._usuarias.get(contexto.usuaria_ref)
        if dados is None:
            # Igual ao adaptador real: referência que não é de uma sessão conhecida.
            raise ErroFerramenta("contexto_ausente")
        metodo = {
            OperacaoFinanceira.RESUMO_TRANSACOES: self._resumo_transacoes,
            OperacaoFinanceira.LISTAR_CONTAS: self._listar_contas,
            OperacaoFinanceira.SITUACAO_RESERVA: self._situacao_reserva,
        }[operacao]
        resultado = metodo(dados, parametros, contexto.data_referencia)
        if resultado is None:
            return None
        valores, localizacao, resumo = resultado
        nome, _, _ = traduzir(operacao, parametros, contexto.data_referencia)
        localizacao = localizacao.model_copy(update={"filtros": _congelar({**localizacao.filtros, "ferramenta": nome})})
        return EvidenciaFinanceira(
            id=id_financeiro(operacao, parametros),
            origem=OrigemFinanceira(operacao=operacao, referencia_api=ROTAS[nome], sintetica=True),
            localizacao=localizacao,
            valores=valores,
            resumo=resumo,
        )

    @staticmethod
    def _resumo_transacoes(dados: dict, p: ParametrosFinanceiros, hoje: date):
        essenciais = {c["id"] for c in dados["categorias"] if c["essencial"]}
        selecionadas = []
        for t in dados["transacoes"]:
            dia = date.fromisoformat(t["data"])
            if p.periodo_inicio and dia < p.periodo_inicio or p.periodo_fim and dia > p.periodo_fim:
                continue
            if p.tipo and t["tipo"] != p.tipo:
                continue
            if p.somente_essenciais and (t["tipo"] != "despesa" or t["categoria_id"] not in essenciais):
                continue
            selecionadas.append(t)
        receitas = sum((Decimal(t["valor"]) for t in selecionadas if t["tipo"] == "receita"), Decimal(0))
        despesas = sum((Decimal(t["valor"]) for t in selecionadas if t["tipo"] == "despesa"), Decimal(0))
        filtros = {}
        if p.tipo:
            filtros["tipo"] = p.tipo
        if p.somente_essenciais:
            filtros["somente_essenciais"] = "true"
        if p.periodo_inicio or p.periodo_fim:
            ini = p.periodo_inicio.strftime("%d/%m/%Y") if p.periodo_inicio else "o início"
            fim = p.periodo_fim.strftime("%d/%m/%Y") if p.periodo_fim else "hoje"
            periodo = f"de {ini} a {fim}"
        else:
            periodo = "em todo o histórico"
        rotulo = "Despesas em categorias essenciais" if p.somente_essenciais else "Transações registradas"
        resumo = (f"{rotulo} {periodo}: {len(selecionadas)} registro(s); receitas {_dinheiro(receitas)}, "
                  f"despesas {_dinheiro(despesas)} BRL.")
        valores = {"receitas": _dinheiro(receitas), "despesas": _dinheiro(despesas),
                   "resultado": _dinheiro(receitas - despesas)}
        local = LocalizacaoFinanceira(periodo_inicio=p.periodo_inicio, periodo_fim=p.periodo_fim,
                                      filtros=filtros, registros=[str(t["id"]) for t in selecionadas])
        return valores, local, resumo

    @staticmethod
    def _listar_contas(dados: dict, p: ParametrosFinanceiros, hoje: date):
        contas = dados["contas"]
        if not contas:
            return None
        valores = {f"conta_{c['id']}": _dinheiro(Decimal(c["saldo_declarado"])) for c in contas}
        total = sum((Decimal(c["saldo_declarado"]) for c in contas), Decimal(0))
        valores["saldo_total_declarado"] = _dinheiro(total)
        nomes = ", ".join(f"{c['nome']} ({_dinheiro(Decimal(c['saldo_declarado']))})" for c in contas)
        resumo = f"{len(contas)} conta(s) declarada(s): {nomes}; total {_dinheiro(total)} BRL."
        local = LocalizacaoFinanceira(registros=[str(c["id"]) for c in contas])
        return valores, local, resumo

    @staticmethod
    def _situacao_reserva(dados: dict, p: ParametrosFinanceiros, hoje: date):
        """Mesma regra da BE-05 (``apps/api/financas/reserva.py``).

        Despesas mensais = média das despesas essenciais dos 3 últimos meses
        completos, contando só meses com registro; meta = mensais × meses de
        cobertura; arredondamento de duas casas com metade para cima.
        """
        def arredondar(valor: Decimal) -> Decimal:
            return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)

        def somar_meses(mes: date, quantidade: int) -> date:
            total = mes.year * 12 + mes.month - 1 + quantidade
            return date(total // 12, total % 12 + 1, 1)

        inicio = somar_meses(hoje.replace(day=1), -3)
        fim_exclusivo = hoje.replace(day=1)
        essenciais = {c["id"] for c in dados["categorias"] if c["essencial"]}
        despesas = [t for t in dados["transacoes"] if t["tipo"] == "despesa" and t["categoria_id"] in essenciais
                    and inicio <= date.fromisoformat(t["data"]) < fim_exclusivo]
        meses = len({t["data"][:7] for t in despesas})
        mensais = arredondar(sum((Decimal(t["valor"]) for t in despesas), Decimal(0)) / meses) if meses else None

        r = dados.get("reserva") or {}
        cobertura = r.get("meses_cobertura")
        saldo = None
        if r:
            saldo = (Decimal(r["saldo_inicial"]) + sum(map(Decimal, r["aportes"]), Decimal(0))
                     - sum(map(Decimal, r["retiradas"]), Decimal(0)))
        faltando = [nome for nome, valor in (("despesas_essenciais", mensais), ("meses_cobertura", cobertura),
                                             ("saldo_inicial", saldo)) if valor is None]
        meta = arredondar(mensais * cobertura) if mensais is not None and cobertura is not None else None
        progresso = None
        if faltando:
            estado = "dados_insuficientes"
        elif meta <= 0:
            estado = "meta_zero"
        else:
            estado, progresso = "calculado", arredondar(100 * saldo / meta)
        falta = max(meta - saldo, Decimal(0)) if meta is not None and saldo is not None else None
        valores = {"meta": _dinheiro(meta) if meta is not None else None,
                   "saldo_declarado": _dinheiro(saldo) if saldo is not None else None,
                   "falta": _dinheiro(falta) if falta is not None else None,
                   "progresso_percentual": _dinheiro(progresso) if progresso is not None else None}
        local = LocalizacaoFinanceira(periodo_inicio=inicio, periodo_fim=fim_exclusivo - timedelta(days=1))
        return valores, local, resumo_reserva(valores, estado, faltando)
