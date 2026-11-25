"""Ferramentas LangChain do Research Agent (S4-02 / #76).

Duas ferramentas, no formato que um LLM com *tool calling* enxerga:

- ``buscar_documentos(consulta)``: busca no corpus educativo por meio de um
  ``BaseRetriever`` do LangChain.
- ``consultar_financeiro(operacao, periodo_inicio, periodo_fim, tipo,
  somente_essenciais)``: executa uma operação da lista fechada
  ``OperacaoFinanceira`` sobre os dados da usuária autenticada.

Três decisões de segurança estão aqui:

1. **Identidade fora do schema.** As ferramentas recebem o
   ``ContextoAutorizado`` por ``RunnableConfig`` (``configurable.contexto``).
   O LangChain não expõe parâmetros ``config`` ao modelo, então a usuária
   nunca aparece entre os argumentos que o LLM preenche.
2. **Permissão checada na própria ferramenta.** Mesmo chamada fora do agente,
   a ferramenta recusa sem contexto ou sem a permissão correspondente.
3. **Resultado como artefato.** ``response_format="content_and_artifact"``:
   o modelo recebe só um resumo curto; as evidências tipadas vão no
   ``ToolMessage.artifact`` para o código.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Callable, Literal, Protocol, runtime_checkable

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, ConfigDict, Field

from .contratos import (
    ChamadaFerramenta,
    ContextoAutorizado,
    EvidenciaDocumental,
    EvidenciaFinanceira,
    LocalizacaoDocumental,
    OperacaoFinanceira,
    OrigemDocumental,
    ParametrosFinanceiros,
    Permissao,
)


class ErroFerramenta(Exception):
    """Falha esperada de uma ferramenta, com código estável para logs."""

    def __init__(self, codigo: str):
        self.codigo = codigo
        super().__init__(codigo)


# --------------------------------------------------------------------------
# Fonte financeira: implementada por fixture (protótipo) ou pelo backend
# --------------------------------------------------------------------------


@runtime_checkable
class FonteFinanceira(Protocol):
    sintetico: bool

    def consultar(self, contexto: ContextoAutorizado, operacao: OperacaoFinanceira,
                  parametros: ParametrosFinanceiros) -> EvidenciaFinanceira | None:
        """Evidência, ``None`` se não houver dados, ou ``ErroFerramenta``.

        Deve filtrar por ``contexto.usuaria_ref`` e tratar dado de outra
        usuária como inexistente.
        """


def id_financeiro(operacao: OperacaoFinanceira, parametros: ParametrosFinanceiros) -> str:
    """ID estável da consulta, sem identificar a usuária."""
    operacao = OperacaoFinanceira(operacao)
    chave = json.dumps([operacao.value, parametros.model_dump(mode="json")], sort_keys=True)
    return f"fin:{operacao.value}:{hashlib.sha256(chave.encode()).hexdigest()[:12]}"


# --------------------------------------------------------------------------
# Retrievers: documentos do contrato v1 da recuperação (S2-05 / #67)
# --------------------------------------------------------------------------

CAMPOS_V1 = ("chunk_id", "document_id", "source_sha256", "page_number", "start", "end", "score")


def documento_de_trecho_v1(item: dict, *, titulos: dict[str, str], sintetica: bool) -> Document:
    """Item do contrato v1 da #67 → ``Document`` do LangChain com proveniência."""
    metadata = {campo: item[campo] for campo in CAMPOS_V1}
    metadata.update(titulo=titulos.get(item["document_id"]), sintetica=sintetica)
    return Document(page_content=item["text"], metadata=metadata)


def evidencia_de_documento(doc: Document, consulta: str) -> EvidenciaDocumental:
    """``Document`` → ``EvidenciaDocumental``. Lança ValidationError/KeyError se faltar proveniência."""
    m = doc.metadata
    return EvidenciaDocumental(
        id="doc:" + str(m["chunk_id"])[:16],
        origem=OrigemDocumental(document_id=m["document_id"], source_sha256=m["source_sha256"],
                                titulo=m.get("titulo"), sintetica=m["sintetica"]),
        localizacao=LocalizacaoDocumental(pagina=m["page_number"], inicio=m["start"], fim=m["end"],
                                          chunk_id=m["chunk_id"]),
        trecho=doc.page_content,
        score=round(float(m["score"]), 4),
        consulta=consulta,
    )


def titulos_do_catalogo(caminho: Path) -> dict[str, str]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {f["id"]: f["title"] for f in dados.get("sources", []) if f.get("title")}


class RetrieverChroma(BaseRetriever):
    """Retriever real sobre ``finance_ai.retrieval.search_evidence`` (#67).

    Enquanto a #67 não estiver na main, levanta ``retrieval_indisponivel``.
    """

    db_path: Path
    colecao: str
    k: int = 5
    min_score: float | None = None
    titulos: dict[str, str] = Field(default_factory=dict)
    busca: Callable[..., dict] | None = Field(default=None, exclude=True)
    sintetico: bool = False

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        busca = self.busca
        if busca is None:
            try:
                from finance_ai.retrieval import search_evidence as busca
            except ImportError as exc:
                raise ErroFerramenta("retrieval_indisponivel") from exc
        extras = {} if self.min_score is None else {"min_score": self.min_score}
        resposta = busca(self.db_path, self.colecao, query, limit=self.k, **extras)
        if resposta.get("status") == "error":
            raise ErroFerramenta(str(resposta.get("error") or "retrieval_error"))
        if resposta.get("status") != "ok":
            return []
        return [documento_de_trecho_v1(i, titulos=self.titulos, sintetica=False)
                for i in resposta.get("evidencias", [])]


# --------------------------------------------------------------------------
# Ferramentas LangChain
# --------------------------------------------------------------------------

FERRAMENTA_DOCS = "buscar_documentos"
FERRAMENTA_FIN = "consultar_financeiro"
NOME_NO_CONTRATO = {FERRAMENTA_DOCS: "documentos.buscar", FERRAMENTA_FIN: "financeiro.consultar"}


class ArgsBusca(BaseModel):
    """Argumentos que o modelo preenche para buscar documentos."""

    model_config = ConfigDict(extra="forbid")
    consulta: str = Field(min_length=1, max_length=500,
                          description="Texto de busca sobre educação financeira, sem dados pessoais.")


class ArgsFinanceiro(BaseModel):
    """Argumentos que o modelo preenche. Não existe campo de usuária."""

    model_config = ConfigDict(extra="forbid")
    operacao: OperacaoFinanceira = Field(description=(
        "resumo_transacoes: totais de receitas e despesas; listar_contas: saldos declarados; "
        "situacao_reserva: meta e progresso da reserva de emergência."))
    periodo_inicio: date | None = Field(default=None, description="Início do período (AAAA-MM-DD).")
    periodo_fim: date | None = Field(default=None, description="Fim do período (AAAA-MM-DD).")
    tipo: Literal["receita", "despesa"] | None = None
    somente_essenciais: bool = Field(default=False, description="Só despesas de categorias essenciais.")


def contexto_da_config(config: RunnableConfig | None) -> ContextoAutorizado:
    contexto = ((config or {}).get("configurable") or {}).get("contexto")
    if not isinstance(contexto, ContextoAutorizado):
        raise ErroFerramenta("contexto_ausente")
    return contexto


def _exigir(contexto: ContextoAutorizado, permissao: Permissao) -> None:
    if permissao not in contexto.permissoes:
        raise ErroFerramenta("permissao_ausente")


def criar_ferramentas(retriever: BaseRetriever, fonte: FonteFinanceira, *, max_trechos: int = 5) -> list[BaseTool]:
    """Cria as duas ferramentas ligadas às implementações recebidas."""

    @tool(FERRAMENTA_DOCS, args_schema=ArgsBusca, response_format="content_and_artifact")
    def buscar_documentos(consulta: str, config: RunnableConfig) -> tuple[str, list[EvidenciaDocumental]]:
        """Busca trechos no acervo de educação financeira. Use para conceitos, dicas e orientações."""
        _exigir(contexto_da_config(config), Permissao.DOCUMENTOS_LER)
        docs = retriever.invoke(consulta, config=config)[:max_trechos]
        evidencias = [evidencia_de_documento(d, consulta) for d in docs]
        return f"{len(evidencias)} trecho(s) encontrado(s).", evidencias

    @tool(FERRAMENTA_FIN, args_schema=ArgsFinanceiro, response_format="content_and_artifact")
    def consultar_financeiro(
        operacao: OperacaoFinanceira,
        config: RunnableConfig,
        periodo_inicio: date | None = None,
        periodo_fim: date | None = None,
        tipo: Literal["receita", "despesa"] | None = None,
        somente_essenciais: bool = False,
    ) -> tuple[str, list[EvidenciaFinanceira]]:
        """Consulta dados financeiros que a própria usuária registrou no aplicativo (somente leitura)."""
        contexto = contexto_da_config(config)
        _exigir(contexto, Permissao.FINANCEIRO_LER)
        parametros = ParametrosFinanceiros(periodo_inicio=periodo_inicio, periodo_fim=periodo_fim,
                                           tipo=tipo, somente_essenciais=somente_essenciais)
        evidencia = fonte.consultar(contexto, OperacaoFinanceira(operacao), parametros)
        if evidencia is None:
            return "Nenhum dado encontrado.", []
        return evidencia.resumo, [evidencia]

    return [buscar_documentos, consultar_financeiro]


def chamada_de_tool_call(tool_call: dict) -> ChamadaFerramenta:
    """Converte um ``tool_call`` do LangChain no contrato ``ChamadaFerramenta``.

    Lança ``ValueError``/``ValidationError`` para ferramenta desconhecida ou
    argumentos fora do schema (ex.: ``usuaria_id``).
    """
    nome, args = tool_call.get("name"), dict(tool_call.get("args") or {})
    if nome == FERRAMENTA_DOCS:
        return ChamadaFerramenta.model_validate({"ferramenta": "documentos.buscar", **args})
    if nome == FERRAMENTA_FIN:
        operacao = args.pop("operacao", None)
        return ChamadaFerramenta.model_validate(
            {"ferramenta": "financeiro.consultar", "operacao": operacao, "parametros": args})
    raise ValueError(f"ferramenta desconhecida: {nome!r}")


def tool_call_de_chamada(chamada: ChamadaFerramenta, indice: int) -> dict:
    """Contrato → ``ToolCall`` para invocar a ferramenta LangChain."""
    if chamada.ferramenta == "documentos.buscar":
        nome, args = FERRAMENTA_DOCS, {"consulta": chamada.consulta}
    else:
        nome = FERRAMENTA_FIN
        args = {"operacao": chamada.operacao.value,
                **(chamada.parametros or ParametrosFinanceiros()).model_dump(mode="json")}
    return {"name": nome, "args": args, "id": f"chamada-{indice}", "type": "tool_call"}
