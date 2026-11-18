"""Política de fluxo entre os agentes: aprovação, abstenção e falha (S4-01 / #75).

Este módulo é a especificação executável que o orquestrador (S4-06 / #80) vai
seguir. Ele não chama modelos nem ferramentas: só decide, a partir da saída
de uma etapa, qual é a próxima. Por ser determinístico, cada regra tem teste.

Estados possíveis::

    PESQUISA ─► ANALISE ─► VALIDACAO ─► COMUNICACAO ─► RESPONDIDA
       │           │           │  ▲            │
       │           │           └──┘ (1 revisão) │
       ▼           ▼           ▼                ▼
    ABSTENCAO  PEDIDO_COMPLEMENTO  ABSTENCAO   FALHA
    FALHA      FALHA

Três desfechos que não são "respondida", com significados diferentes:

- **abstenção**: o sistema funcionou, mas não há base para afirmar nada
  (sem evidências, ou a validação reprovou). Dizer "não sei" é correto.
- **pedido de complemento**: falta um dado que só a usuária pode informar
  (ex.: nenhuma categoria marcada como essencial).
- **falha**: algum componente quebrou (erro, tempo esgotado, contrato inválido).
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

from pydantic import ValidationError

from .contratos import (
    Contrato,
    ContextoAutorizado,
    EtapaRastro,
    Lacuna,
    MotivoEncerramento,
    Papel,
    RespostaFinal,
    SaidaAnalise,
    SaidaComunicacao,
    SaidaPesquisa,
    SaidaValidacao,
)

MAX_REVISOES_PADRAO = 1
"""Quantas vezes a Analysis pode refazer o trabalho após uma reprovação."""


class Etapa(StrEnum):
    PESQUISA = "pesquisa"
    ANALISE = "analise"
    VALIDACAO = "validacao"
    COMUNICACAO = "comunicacao"
    RESPONDIDA = "respondida"
    ABSTENCAO = "abstencao"
    PEDIDO_COMPLEMENTO = "pedido_complemento"
    FALHA = "falha"


ETAPAS_FINAIS = frozenset({Etapa.RESPONDIDA, Etapa.ABSTENCAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA})


class Transicao(Contrato):
    proxima: Etapa
    motivo: MotivoEncerramento | None = None
    feedback: list[str] = []


# --------------------------------------------------------------------------
# Leitura segura de contratos
# --------------------------------------------------------------------------

C = TypeVar("C", bound=Contrato)


class ContratoInvalido(Exception):
    """Saída de agente que não respeita o schema. Vira falha da etapa."""

    def __init__(self, modelo: str, erros: list[dict]):
        self.modelo = modelo
        self.erros = erros
        super().__init__(f"{modelo}: {len(erros)} erro(s) de contrato")


def ler_contrato(modelo: type[C], dados: object) -> C:
    """Valida ``dados`` (dict ou JSON) contra ``modelo``.

    Use na fronteira de cada agente, principalmente quando a saída vem de um
    LLM: o texto gerado é não confiável até passar por aqui.
    """
    try:
        if isinstance(dados, (str, bytes)):
            return modelo.model_validate_json(dados)
        return modelo.model_validate(dados)
    except ValidationError as exc:
        erros = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        raise ContratoInvalido(modelo.__name__, erros) from None


# --------------------------------------------------------------------------
# Transições
# --------------------------------------------------------------------------


def apos_pesquisa(saida: SaidaPesquisa) -> Transicao:
    if saida.status == "falha":
        return Transicao(proxima=Etapa.FALHA, motivo=MotivoEncerramento.FALHA_PESQUISA)
    if saida.status == "sem_evidencias":
        return Transicao(proxima=Etapa.ABSTENCAO, motivo=MotivoEncerramento.SEM_EVIDENCIAS)
    return Transicao(proxima=Etapa.ANALISE)


def apos_analise(saida: SaidaAnalise) -> Transicao:
    if saida.status == "falha":
        return Transicao(proxima=Etapa.FALHA, motivo=MotivoEncerramento.FALHA_ANALISE)
    if saida.status == "dados_insuficientes":
        return Transicao(proxima=Etapa.PEDIDO_COMPLEMENTO, motivo=MotivoEncerramento.DADOS_INSUFICIENTES)
    return Transicao(proxima=Etapa.VALIDACAO)


def apos_validacao(
    saida: SaidaValidacao, revisoes_realizadas: int, max_revisoes: int = MAX_REVISOES_PADRAO
) -> Transicao:
    """Reprovação devolve à Analysis uma vez com feedback; depois, abstenção.

    A análise reprovada nunca segue para a Communication.
    """
    if saida.decisao == "reprovada":
        if revisoes_realizadas < max_revisoes:
            return Transicao(proxima=Etapa.ANALISE, feedback=list(saida.feedback))
        return Transicao(proxima=Etapa.ABSTENCAO, motivo=MotivoEncerramento.VALIDACAO_REPROVADA)
    return Transicao(proxima=Etapa.COMUNICACAO)


def inconsistencias_comunicacao(
    pesquisa: SaidaPesquisa, analise: SaidaAnalise, validacao: SaidaValidacao, saida: SaidaComunicacao
) -> list[str]:
    """Checagem determinística final: a Communication não pode inventar suporte.

    - só usa afirmações aprovadas;
    - cada afirmação mantém as evidências que a Analysis indicou;
    - toda fonte citada existe na pesquisa desta requisição.
    """
    problemas: list[str] = []
    aprovadas = set(validacao.afirmacoes_aprovadas)
    evid_por_afirmacao = {a.id: set(a.evidencias_ids) for a in analise.afirmacoes}
    existentes = {e.id for e in pesquisa.evidencias}

    for lig in saida.ligacoes:
        if lig.afirmacao_id not in aprovadas:
            problemas.append(f"afirmação {lig.afirmacao_id} não foi aprovada")
            continue
        extras = set(lig.evidencias_ids) - evid_por_afirmacao.get(lig.afirmacao_id, set())
        if extras:
            problemas.append(f"afirmação {lig.afirmacao_id} ligada a evidência não indicada: {sorted(extras)}")
    for fonte in saida.fontes:
        if fonte.evidencia_id not in existentes:
            problemas.append(f"fonte {fonte.evidencia_id} não existe na pesquisa")
    return problemas


def apos_comunicacao(
    pesquisa: SaidaPesquisa, analise: SaidaAnalise, validacao: SaidaValidacao, saida: SaidaComunicacao
) -> Transicao:
    if inconsistencias_comunicacao(pesquisa, analise, validacao, saida):
        return Transicao(proxima=Etapa.FALHA, motivo=MotivoEncerramento.COMUNICACAO_INCONSISTENTE)
    return Transicao(proxima=Etapa.RESPONDIDA)


def falha_de_etapa(papel: Papel, *, tempo_esgotado: bool = False, contrato: bool = False) -> Transicao:
    """Exceção, timeout ou contrato inválido em qualquer agente."""
    if tempo_esgotado:
        motivo = MotivoEncerramento.TEMPO_ESGOTADO
    elif contrato:
        motivo = MotivoEncerramento.CONTRATO_INVALIDO
    else:
        motivo = {
            Papel.RESEARCH: MotivoEncerramento.FALHA_PESQUISA,
            Papel.ANALYSIS: MotivoEncerramento.FALHA_ANALISE,
            Papel.VALIDATION: MotivoEncerramento.FALHA_VALIDACAO,
            Papel.COMMUNICATION: MotivoEncerramento.FALHA_COMUNICACAO,
        }.get(papel, MotivoEncerramento.CONTRATO_INVALIDO)
    return Transicao(proxima=Etapa.FALHA, motivo=motivo)


# --------------------------------------------------------------------------
# Respostas finais
# --------------------------------------------------------------------------

LIMITE_PADRAO = (
    "Valores financeiros são os declarados por você no aplicativo, sem conexão com bancos."
)

MENSAGENS_SEGURAS: dict[MotivoEncerramento, str] = {
    MotivoEncerramento.SEM_EVIDENCIAS: (
        "Não encontrei informações suficientes nos documentos e nos dados cadastrados "
        "para responder com segurança. Você pode reformular a pergunta?"
    ),
    MotivoEncerramento.VALIDACAO_REPROVADA: (
        "Não consegui confirmar a resposta com as fontes disponíveis, então prefiro "
        "não afirmar algo que possa estar errado."
    ),
    MotivoEncerramento.DADOS_INSUFICIENTES: (
        "Para responder, preciso de mais algumas informações."
    ),
}
MENSAGEM_FALHA = (
    "Não foi possível concluir sua pergunta agora. Nenhum dado seu foi alterado. "
    "Tente novamente em instantes."
)


def resposta_segura(
    contexto: ContextoAutorizado,
    final: Etapa,
    motivo: MotivoEncerramento,
    etapas: list[EtapaRastro],
    lacunas: list[Lacuna] | None = None,
) -> RespostaFinal:
    """Texto fixo, sem LLM, para abstenção, pedido de complemento ou falha.

    Não reaproveita nenhum texto da análise reprovada.
    """
    if final not in (Etapa.ABSTENCAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA):
        raise ValueError("resposta_segura não se aplica a respostas aprovadas")
    perguntas = []
    if final is Etapa.PEDIDO_COMPLEMENTO:
        perguntas = [l.pergunta_complemento or l.descricao for l in (lacunas or [])]
    texto = MENSAGEM_FALHA if final is Etapa.FALHA else MENSAGENS_SEGURAS[motivo]
    return RespostaFinal(
        correlation_id=contexto.correlation_id,
        estado=final.value,
        texto=texto,
        perguntas_complemento=perguntas,
        motivo=motivo,
        limites=[LIMITE_PADRAO],
        etapas=etapas,
    )


def resposta_aprovada(
    contexto: ContextoAutorizado, comunicacao: SaidaComunicacao, etapas: list[EtapaRastro]
) -> RespostaFinal:
    limites = list(comunicacao.limites) or [LIMITE_PADRAO]
    return RespostaFinal(
        correlation_id=contexto.correlation_id,
        estado="respondida",
        texto=comunicacao.texto,
        fontes=comunicacao.fontes,
        limites=limites,
        etapas=etapas,
    )
