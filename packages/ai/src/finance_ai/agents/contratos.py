"""Contratos de dados entre o orquestrador e os quatro agentes (S4-01 / #75).

Cada agente recebe uma *entrada* e devolve uma *saída* tipada. O orquestrador
valida as duas pontas antes de seguir para a próxima etapa. Se a saída de um
agente (ou de um LLM dentro dele) não respeitar o contrato, ela é tratada como
falha da etapa, nunca como resposta.

Convenções usadas em todos os modelos:

- ``extra="forbid"``: campos desconhecidos são recusados. Assim, um modelo de
  linguagem não consegue "inventar" um ``usuaria_id`` ou um parâmetro de
  ferramenta fora do previsto.
- ``frozen=True``: objetos imutáveis; uma etapa não altera a saída da anterior.
- Valores monetários trafegam como texto decimal (``"1234.56"``), igual à API
  financeira (BE-03/BE-04), para não perder precisão com ``float``.
- IDs de evidência carregam o tipo no prefixo: ``doc:`` para trechos do corpus
  educativo e ``fin:`` para resultados de ferramentas financeiras.

Os JSON Schemas em ``contracts/agentes/schemas`` são gerados a partir destes
modelos por ``scripts/exportar_schemas_agentes.py``. Não edite os ``.json``
manualmente: altere o modelo, regenere e revise o diff.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

VERSAO_CONTRATOS = "1.0"

# --------------------------------------------------------------------------
# Tipos básicos reutilizados
# --------------------------------------------------------------------------

CorrelationId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,64}$")]
"""Identificador de rastreio de uma requisição de chat, igual nos logs e na resposta."""

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

ValorDecimal = Annotated[str, StringConstraints(pattern=r"^-?\d{1,12}\.\d{2}$")]
"""Valor monetário como texto, com ponto e duas casas: ``"-20.00"``, ``"6000.00"``."""

IdEvidenciaDocumental = Annotated[str, StringConstraints(pattern=r"^doc:[0-9a-f]{16,64}$")]
IdEvidenciaFinanceira = Annotated[
    str, StringConstraints(pattern=r"^fin:[a-z_]{3,40}:[0-9a-f]{12}$")
]
IdEvidencia = Annotated[str, StringConstraints(pattern=r"^(doc:[0-9a-f]{16,64}|fin:[a-z_]{3,40}:[0-9a-f]{12})$")]

IdAfirmacao = Annotated[str, StringConstraints(pattern=r"^a[0-9]{1,3}$")]
"""Afirmações são numeradas pela Analysis: ``a1``, ``a2``..."""

TextoCurto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class Contrato(BaseModel):
    """Base de todos os contratos: imutável e sem campos extras."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------
# Contexto autorizado: o que o backend entrega à camada de IA
# --------------------------------------------------------------------------


class Papel(StrEnum):
    RESEARCH = "research"
    ANALYSIS = "analysis"
    VALIDATION = "validation"
    COMMUNICATION = "communication"
    ORQUESTRADOR = "orquestrador"


class Permissao(StrEnum):
    """Escopos de leitura que o backend concede para a requisição.

    Não existe permissão de escrita: nenhum agente cria, altera ou exclui
    registros financeiros. Escrita passa pela API com confirmação da usuária.
    """

    DOCUMENTOS_LER = "documentos:ler"
    FINANCEIRO_LER = "financeiro:ler"


class ContextoAutorizado(Contrato):
    """Montado pelo backend a partir da sessão autenticada, nunca pelo modelo.

    ``usuaria_ref`` é uma referência opaca. Ela é repassada às ferramentas pelo
    código do agente, e não aparece em prompts nem em parâmetros que um LLM
    possa preencher. Mesmo assim, cada ferramenta revalida o acesso.
    """

    correlation_id: CorrelationId
    usuaria_ref: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{4,64}$")]
    conversa_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{4,64}$")]
    permissoes: Annotated[list[Permissao], Field(max_length=2)]
    data_referencia: date = Field(description="Data atual em America/Sao_Paulo; base para 'este mês'.")
    memoria: Annotated[
        list[Annotated[str, StringConstraints(max_length=500)]], Field(max_length=5)
    ] = Field(default_factory=list, description="Resumo limitado da conversa, já filtrado pelo backend.")

    @model_validator(mode="after")
    def _permissoes_unicas(self) -> "ContextoAutorizado":
        if len(set(self.permissoes)) != len(self.permissoes):
            raise ValueError("permissões repetidas")
        return self


# --------------------------------------------------------------------------
# Evidências (produzidas pelo Research Agent)
# --------------------------------------------------------------------------


class OrigemDocumental(Contrato):
    tipo_origem: Literal["corpus_educativo"] = "corpus_educativo"
    document_id: Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,4}[0-9]{3}$")] = Field(
        description="ID do catálogo de fontes (ex.: F001) ou de fixture sintética (ex.: SYN001)."
    )
    source_sha256: Sha256
    titulo: TextoCurto | None = None
    sintetica: bool = Field(description="true quando vem de fixture de teste, não do acervo real.")


class LocalizacaoDocumental(Contrato):
    pagina: Annotated[int, Field(ge=1)] = Field(description="Página física do PDF, começando em 1.")
    inicio: Annotated[int, Field(ge=0)] = Field(description="Offset inicial (inclusivo) no texto limpo da página.")
    fim: Annotated[int, Field(ge=1)] = Field(description="Offset final (exclusivo) no texto limpo da página.")
    chunk_id: Sha256

    @model_validator(mode="after")
    def _intervalo(self) -> "LocalizacaoDocumental":
        if self.fim <= self.inicio:
            raise ValueError("fim deve ser maior que inicio")
        return self


class EvidenciaDocumental(Contrato):
    """Trecho do corpus educativo. Nunca representa dado pessoal da usuária."""

    tipo: Literal["documental"] = "documental"
    id: IdEvidenciaDocumental
    origem: OrigemDocumental
    localizacao: LocalizacaoDocumental
    trecho: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    score: Annotated[float, Field(ge=-1, le=1)] = Field(
        description="Similaridade de cosseno da busca. Não é probabilidade de correção."
    )
    consulta: Annotated[str, StringConstraints(min_length=1, max_length=500)] = Field(
        description="Texto de busca que recuperou o trecho."
    )

    @model_validator(mode="after")
    def _id_coerente(self) -> "EvidenciaDocumental":
        if not self.localizacao.chunk_id.startswith(self.id.removeprefix("doc:")):
            raise ValueError("id documental deve ser derivado do chunk_id")
        return self


class OperacaoFinanceira(StrEnum):
    """Lista fechada de consultas financeiras. Não há SQL livre nem escrita."""

    RESUMO_TRANSACOES = "resumo_transacoes"
    LISTAR_CONTAS = "listar_contas"
    SITUACAO_RESERVA = "situacao_reserva"


class ParametrosFinanceiros(Contrato):
    """Parâmetros que o planejador (regra ou LLM) pode preencher.

    Repare que não existe campo de usuária: quem é a dona dos dados vem do
    ``ContextoAutorizado``, e ``extra="forbid"`` recusa qualquer tentativa.
    """

    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    tipo: Literal["receita", "despesa"] | None = None
    somente_essenciais: bool = False

    @model_validator(mode="after")
    def _periodo(self) -> "ParametrosFinanceiros":
        if self.periodo_inicio and self.periodo_fim and self.periodo_fim < self.periodo_inicio:
            raise ValueError("periodo_fim anterior a periodo_inicio")
        return self


class OrigemFinanceira(Contrato):
    tipo_origem: Literal["dados_declarados"] = "dados_declarados"
    operacao: OperacaoFinanceira
    referencia_api: Annotated[str, StringConstraints(max_length=120)] = Field(
        description="Rota ou serviço do backend equivalente, para rastreio (ex.: GET /api/transacoes)."
    )
    sintetica: bool


class LocalizacaoFinanceira(Contrato):
    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    filtros: dict[str, str] = Field(default_factory=dict)
    registros: Annotated[list[str], Field(max_length=200)] = Field(
        default_factory=list, description="IDs dos registros considerados, quando aplicável."
    )


class EvidenciaFinanceira(Contrato):
    """Resultado determinístico de uma ferramenta do backend, já autorizado."""

    tipo: Literal["financeira"] = "financeira"
    id: IdEvidenciaFinanceira
    origem: OrigemFinanceira
    localizacao: LocalizacaoFinanceira
    moeda: Literal["BRL"] = "BRL"
    valores: dict[Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,39}$")], ValorDecimal | None] = Field(
        description="Valores calculados pelo backend. None quando não se aplica (ex.: progresso com meta zero)."
    )
    resumo: Annotated[str, StringConstraints(min_length=1, max_length=500)] = Field(
        description="Descrição gerada pela ferramenta (não pelo LLM) do que os valores significam."
    )

    @model_validator(mode="after")
    def _id_coerente(self) -> "EvidenciaFinanceira":
        if not self.id.startswith(f"fin:{self.origem.operacao.value}:"):
            raise ValueError("id financeiro deve conter a operação de origem")
        return self


Evidencia = Annotated[Union[EvidenciaDocumental, EvidenciaFinanceira], Field(discriminator="tipo")]


def _ids_unicos(ids: list[str], nome: str) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError(f"{nome} com IDs repetidos")


# --------------------------------------------------------------------------
# Research Agent
# --------------------------------------------------------------------------


class LimitesPesquisa(Contrato):
    max_trechos: Annotated[int, Field(ge=1, le=10)] = 5
    max_chamadas: Annotated[int, Field(ge=1, le=6)] = 4


class EntradaPesquisa(Contrato):
    contexto: ContextoAutorizado
    pergunta: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    limites: LimitesPesquisa = Field(default_factory=LimitesPesquisa)


class ChamadaFerramenta(Contrato):
    """Uma chamada planejada. É isso que um LLM preencheria em *tool calling*."""

    ferramenta: Literal["documentos.buscar", "financeiro.consultar"]
    consulta: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None
    operacao: OperacaoFinanceira | None = None
    parametros: ParametrosFinanceiros | None = None

    @model_validator(mode="after")
    def _forma(self) -> "ChamadaFerramenta":
        if self.ferramenta == "documentos.buscar":
            if not self.consulta or self.operacao or self.parametros:
                raise ValueError("documentos.buscar exige somente 'consulta'")
        elif self.consulta or not self.operacao:
            raise ValueError("financeiro.consultar exige 'operacao' e não aceita 'consulta'")
        return self


class RegistroChamada(Contrato):
    """Rastro de cada chamada executada; vai para logs e para a avaliação."""

    ferramenta: Literal["documentos.buscar", "financeiro.consultar"]
    operacao: OperacaoFinanceira | None = None
    status: Literal["ok", "sem_resultados", "negada", "erro"]
    codigo_erro: Annotated[str, StringConstraints(pattern=r"^[a-z_]{3,40}$")] | None = None
    evidencias_ids: list[IdEvidencia] = Field(default_factory=list)
    duracao_ms: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _coerencia(self) -> "RegistroChamada":
        if self.status in ("negada", "erro") and not self.codigo_erro:
            raise ValueError("chamada negada ou com erro exige codigo_erro")
        if self.status == "ok" and not self.evidencias_ids:
            raise ValueError("chamada ok deve produzir evidências")
        if self.status != "ok" and self.evidencias_ids:
            raise ValueError("somente chamada ok produz evidências")
        return self


class SaidaPesquisa(Contrato):
    versao: Literal["1.0"] = VERSAO_CONTRATOS
    status: Literal["concluida", "parcial", "sem_evidencias", "falha"]
    modo: Literal["prototipo_fixtures", "integrado"] = Field(
        description="prototipo_fixtures quando alguma ferramenta usa dados sintéticos."
    )
    evidencias: list[Evidencia] = Field(default_factory=list)
    chamadas: list[RegistroChamada] = Field(default_factory=list)
    observacoes: list[TextoCurto] = Field(default_factory=list)

    @model_validator(mode="after")
    def _coerencia(self) -> "SaidaPesquisa":
        ids = [e.id for e in self.evidencias]
        _ids_unicos(ids, "evidencias")
        produzidos = {i for c in self.chamadas for i in c.evidencias_ids}
        if set(ids) != produzidos:
            raise ValueError("evidências devem corresponder às registradas nas chamadas")
        houve_erro = any(c.status in ("erro", "negada") for c in self.chamadas)
        if self.status in ("concluida", "parcial") and not self.evidencias:
            raise ValueError(f"status {self.status} exige ao menos uma evidência")
        if self.status in ("sem_evidencias", "falha") and self.evidencias:
            raise ValueError(f"status {self.status} não pode trazer evidências")
        if self.status == "concluida" and houve_erro:
            raise ValueError("houve chamada negada/com erro: use 'parcial'")
        if self.status == "parcial" and not houve_erro:
            raise ValueError("'parcial' exige ao menos uma chamada negada/com erro")
        if self.status == "falha" and not houve_erro:
            raise ValueError("'falha' exige ao menos uma chamada negada/com erro")
        if self.modo == "integrado" and any(e.origem.sintetica for e in self.evidencias):
            raise ValueError("modo integrado não pode conter evidência sintética")
        return self


# --------------------------------------------------------------------------
# Analysis Agent
# --------------------------------------------------------------------------


class Afirmacao(Contrato):
    """Uma frase verificável, sempre ligada a evidências."""

    id: IdAfirmacao
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
    natureza: Literal["dado_pessoal", "calculo", "orientacao_educativa"]
    evidencias_ids: Annotated[list[IdEvidencia], Field(min_length=1, max_length=10)]


class Lacuna(Contrato):
    """Informação que faltou para responder; vira pedido de complemento."""

    codigo: Literal[
        "periodo_nao_informado",
        "sem_dados_financeiros",
        "sem_categoria_essencial",
        "sem_fonte_documental",
        "pergunta_ambigua",
    ]
    descricao: TextoCurto
    pergunta_complemento: TextoCurto | None = None


class EntradaAnalise(Contrato):
    contexto: ContextoAutorizado
    pergunta: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    pesquisa: SaidaPesquisa
    feedback_validacao: list[TextoCurto] = Field(
        default_factory=list, description="Preenchido somente na revisão após uma reprovação."
    )


class SaidaAnalise(Contrato):
    versao: Literal["1.0"] = VERSAO_CONTRATOS
    status: Literal["analisada", "dados_insuficientes", "falha"]
    afirmacoes: list[Afirmacao] = Field(default_factory=list)
    lacunas: list[Lacuna] = Field(default_factory=list)
    codigo_erro: Annotated[str, StringConstraints(pattern=r"^[a-z_]{3,40}$")] | None = None

    @model_validator(mode="after")
    def _coerencia(self) -> "SaidaAnalise":
        _ids_unicos([a.id for a in self.afirmacoes], "afirmacoes")
        if self.status == "analisada" and not self.afirmacoes:
            raise ValueError("'analisada' exige ao menos uma afirmação")
        if self.status == "dados_insuficientes" and not self.lacunas:
            raise ValueError("'dados_insuficientes' exige ao menos uma lacuna")
        if self.status == "falha" and (not self.codigo_erro or self.afirmacoes):
            raise ValueError("'falha' exige codigo_erro e nenhuma afirmação")
        if self.status != "falha" and self.codigo_erro:
            raise ValueError("codigo_erro só é usado com status 'falha'")
        return self


# --------------------------------------------------------------------------
# Validation Agent
# --------------------------------------------------------------------------


class RegraValidacao(StrEnum):
    REFERENCIAS_EXISTENTES = "referencias_existentes"
    NATUREZA_COMPATIVEL = "natureza_compativel"
    NUMEROS_CONFEREM = "numeros_conferem"
    SUPORTE_DOCUMENTAL = "suporte_documental"
    ESCOPO_PERMITIDO = "escopo_permitido"


class Verificacao(Contrato):
    regra: RegraValidacao
    resultado: Literal["ok", "alerta", "falha"]
    afirmacao_id: IdAfirmacao | None = None
    detalhe: TextoCurto


class MotivoBloqueio(StrEnum):
    REFERENCIA_INEXISTENTE = "referencia_inexistente"
    NUMERO_DIVERGENTE = "numero_divergente"
    SEM_SUPORTE = "sem_suporte"
    FORA_DO_ESCOPO = "fora_do_escopo"


class EntradaValidacao(Contrato):
    contexto: ContextoAutorizado
    pergunta: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    pesquisa: SaidaPesquisa
    analise: SaidaAnalise

    @model_validator(mode="after")
    def _somente_analisada(self) -> "EntradaValidacao":
        if self.analise.status != "analisada":
            raise ValueError("Validation só recebe análise com status 'analisada'")
        return self


class SaidaValidacao(Contrato):
    versao: Literal["1.0"] = VERSAO_CONTRATOS
    decisao: Literal["aprovada", "aprovada_com_alertas", "reprovada"]
    verificacoes: Annotated[list[Verificacao], Field(min_length=1)]
    afirmacoes_aprovadas: list[IdAfirmacao] = Field(default_factory=list)
    alegacoes_sem_suporte: list[IdAfirmacao] = Field(default_factory=list)
    motivo_bloqueio: MotivoBloqueio | None = None
    feedback: list[TextoCurto] = Field(
        default_factory=list, description="Orientação objetiva para uma revisão da Analysis."
    )

    @model_validator(mode="after")
    def _coerencia(self) -> "SaidaValidacao":
        resultados = {v.resultado for v in self.verificacoes}
        if self.decisao == "reprovada":
            if not self.motivo_bloqueio or "falha" not in resultados:
                raise ValueError("'reprovada' exige motivo_bloqueio e ao menos uma verificação com falha")
            if self.afirmacoes_aprovadas:
                raise ValueError("'reprovada' não aprova afirmações")
        else:
            if "falha" in resultados or self.motivo_bloqueio or self.alegacoes_sem_suporte:
                raise ValueError("aprovação não admite falha, bloqueio ou alegação sem suporte")
            if not self.afirmacoes_aprovadas:
                raise ValueError("aprovação deve listar as afirmações aprovadas")
            tem_alerta = "alerta" in resultados
            if self.decisao == "aprovada" and tem_alerta:
                raise ValueError("há alertas: use 'aprovada_com_alertas'")
            if self.decisao == "aprovada_com_alertas" and not tem_alerta:
                raise ValueError("'aprovada_com_alertas' exige ao menos um alerta")
        return self


# --------------------------------------------------------------------------
# Communication Agent
# --------------------------------------------------------------------------


class FonteCitada(Contrato):
    evidencia_id: IdEvidencia
    rotulo: TextoCurto = Field(description="Como a fonte aparece para a usuária (ex.: 'F003, p. 12').")


class Ligacao(Contrato):
    """Explica qual evidência sustenta cada afirmação usada no texto."""

    afirmacao_id: IdAfirmacao
    evidencias_ids: Annotated[list[IdEvidencia], Field(min_length=1)]


class EntradaComunicacao(Contrato):
    contexto: ContextoAutorizado
    pergunta: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    pesquisa: SaidaPesquisa
    analise: SaidaAnalise
    validacao: SaidaValidacao

    @model_validator(mode="after")
    def _somente_aprovada(self) -> "EntradaComunicacao":
        if self.validacao.decisao == "reprovada":
            raise ValueError("Communication nunca recebe conteúdo reprovado")
        return self


class SaidaComunicacao(Contrato):
    versao: Literal["1.0"] = VERSAO_CONTRATOS
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]
    fontes: Annotated[list[FonteCitada], Field(min_length=1)]
    ligacoes: Annotated[list[Ligacao], Field(min_length=1)]
    limites: list[TextoCurto] = Field(default_factory=list)

    @model_validator(mode="after")
    def _coerencia(self) -> "SaidaComunicacao":
        _ids_unicos([f.evidencia_id for f in self.fontes], "fontes")
        citadas = {f.evidencia_id for f in self.fontes}
        usadas = {i for lig in self.ligacoes for i in lig.evidencias_ids}
        if not usadas <= citadas:
            raise ValueError("toda evidência usada nas ligações deve aparecer em 'fontes'")
        return self


# --------------------------------------------------------------------------
# Resposta final (orquestrador → API → PWA)
# --------------------------------------------------------------------------


class MotivoEncerramento(StrEnum):
    SEM_EVIDENCIAS = "sem_evidencias"
    DADOS_INSUFICIENTES = "dados_insuficientes"
    VALIDACAO_REPROVADA = "validacao_reprovada"
    FALHA_PESQUISA = "falha_pesquisa"
    FALHA_ANALISE = "falha_analise"
    FALHA_VALIDACAO = "falha_validacao"
    FALHA_COMUNICACAO = "falha_comunicacao"
    COMUNICACAO_INCONSISTENTE = "comunicacao_inconsistente"
    CONTRATO_INVALIDO = "contrato_invalido"
    TEMPO_ESGOTADO = "tempo_esgotado"


class EtapaRastro(Contrato):
    papel: Papel
    status: Annotated[str, StringConstraints(pattern=r"^[a-z_]{2,40}$")]
    duracao_ms: Annotated[int, Field(ge=0)]
    codigo: Annotated[str, StringConstraints(pattern=r"^[a-z_]{3,40}$")] | None = None


class RespostaFinal(Contrato):
    versao: Literal["1.0"] = VERSAO_CONTRATOS
    correlation_id: CorrelationId
    estado: Literal["respondida", "abstencao", "pedido_complemento", "falha"]
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]
    fontes: list[FonteCitada] = Field(default_factory=list)
    limites: list[TextoCurto] = Field(default_factory=list)
    perguntas_complemento: list[TextoCurto] = Field(default_factory=list)
    motivo: MotivoEncerramento | None = None
    etapas: list[EtapaRastro] = Field(default_factory=list)

    @model_validator(mode="after")
    def _coerencia(self) -> "RespostaFinal":
        if self.estado == "respondida":
            if not self.fontes or self.motivo is not None:
                raise ValueError("'respondida' exige fontes e não tem motivo")
        else:
            if self.motivo is None:
                raise ValueError(f"'{self.estado}' exige motivo")
            if self.fontes:
                raise ValueError("somente resposta aprovada cita fontes")
        if self.estado == "pedido_complemento" and not self.perguntas_complemento:
            raise ValueError("'pedido_complemento' exige ao menos uma pergunta")
        if self.estado != "pedido_complemento" and self.perguntas_complemento:
            raise ValueError("perguntas_complemento só em 'pedido_complemento'")
        return self


#: Modelos exportados como JSON Schema, na ordem do fluxo.
CONTRATOS_EXPORTADOS: dict[str, type[Contrato]] = {
    "ContextoAutorizado": ContextoAutorizado,
    "EntradaPesquisa": EntradaPesquisa,
    "ChamadaFerramenta": ChamadaFerramenta,
    "SaidaPesquisa": SaidaPesquisa,
    "EntradaAnalise": EntradaAnalise,
    "SaidaAnalise": SaidaAnalise,
    "EntradaValidacao": EntradaValidacao,
    "SaidaValidacao": SaidaValidacao,
    "EntradaComunicacao": EntradaComunicacao,
    "SaidaComunicacao": SaidaComunicacao,
    "RespostaFinal": RespostaFinal,
}
