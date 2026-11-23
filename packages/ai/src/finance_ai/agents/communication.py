"""Communication Agent (S4-05 / #79): redige só o que a Validation aprovou.

A Communication não escolhe fontes nem cria ligações: devolve parágrafos que
declaram quais afirmações aprovadas expressam, e o orquestrador
(``fluxo.montar_resposta``) numera as citações e monta fontes e ligações.

Duas formas de redigir:

- **Modelo (padrão, sem LLM):** agrupa as afirmações aprovadas em parágrafos,
  primeiro os dados da usuária e os cálculos, depois as orientações
  educativas, com o texto da própria afirmação. Não cria conteúdo novo.
- **Redator opcional (ex.: LLM local):** um chamável ``redator(prompt) -> str``
  que devolve JSON com parágrafos. A redação só é usada se passar em todas as
  checagens abaixo; senão, a Communication volta ao modelo.

Checagens da redação do redator:

1. contrato ``SaidaComunicacao`` válido;
2. ``fluxo.inconsistencias_comunicacao``: só afirmações aprovadas, nenhuma
   faltando e nenhum número novo;
3. ``palavras_novas``: cada parágrafo usa no máximo ``MAX_PALAVRAS_NOVAS`` de
   palavras de conteúdo que não estão nas afirmações que ele declara. É a
   avaliação própria do texto que o contrato pede: uma frase nova sem números
   não passa pela checagem 2, mas passa por esta.

Os limites explicam de onde vem o suporte (números entre colchetes), avisam
quando há dados de demonstração ou fontes que não puderam ser consultadas e
reforçam que o conteúdo é educativo.

A reprovação nunca chega aqui: ``EntradaComunicacao`` recusa conteúdo
reprovado, e o orquestrador responde com ``fluxo.resposta_segura``, que é um
texto fixo e não repete nenhuma alegação bloqueada.
"""

from __future__ import annotations

import json
from typing import Callable

from pydantic import ValidationError

from .contratos import EntradaComunicacao, Paragrafo, SaidaComunicacao
from .fluxo import LIMITE_PADRAO, inconsistencias_comunicacao
from .texto import cobertura, curto

MAX_PALAVRAS_NOVAS = 0.4
"""Fração máxima de palavras de conteúdo novas num parágrafo do redator."""

LIMITE_SUPORTE = (
    "Os números entre colchetes indicam a fonte de cada trecho: seus registros no "
    "aplicativo ou um documento educativo."
)
LIMITE_EDUCATIVO = "Conteúdo educativo, sem recomendação de investimento."
LIMITE_SINTETICO = "Parte das informações vem de dados de demonstração (fictícios)."
LIMITE_PARCIAL = (
    "Algumas fontes não puderam ser consultadas nesta conversa; a resposta usa só o que foi acessado."
)
LIMITE_ALERTA = "Algumas orientações têm suporte parcial no documento citado; vale conferir a fonte."

_MAX_POR_PARAGRAFO = 5
_MAX_CARACTERES = 800

Redator = Callable[[str], str]


def palavras_novas(texto: str, referencia: str) -> float:
    """Fração das palavras de conteúdo de ``texto`` ausentes de ``referencia``."""
    return 1.0 - cobertura(texto, referencia)


def _agrupar(textos: list[tuple[str, str]]) -> list[Paragrafo]:
    """Junta (id, texto) em parágrafos que respeitam os limites do contrato."""
    paragrafos: list[Paragrafo] = []
    ids: list[str] = []
    partes: list[str] = []
    for afirmacao_id, texto in textos:
        candidato = " ".join(partes + [texto])
        if ids and (len(ids) == _MAX_POR_PARAGRAFO or len(candidato) > _MAX_CARACTERES):
            paragrafos.append(Paragrafo(afirmacoes_ids=ids, texto=" ".join(partes)))
            ids, partes = [], []
        ids.append(afirmacao_id)
        partes.append(texto)
    if ids:
        paragrafos.append(Paragrafo(afirmacoes_ids=ids, texto=" ".join(partes)))
    return paragrafos


def redigir_por_modelo(entrada: EntradaComunicacao) -> tuple[Paragrafo, ...]:
    aprovadas = set(entrada.validacao.afirmacoes_aprovadas)
    afirmacoes = [a for a in entrada.analise.afirmacoes if a.id in aprovadas]
    dados = [(a.id, a.texto) for a in afirmacoes if a.natureza != "orientacao_educativa"]
    orientacoes = [(a.id, a.texto) for a in afirmacoes if a.natureza == "orientacao_educativa"]
    return tuple(_agrupar(dados) + _agrupar(orientacoes))


def limites(entrada: EntradaComunicacao) -> tuple[str, ...]:
    aprovadas = set(entrada.validacao.afirmacoes_aprovadas)
    usadas = {i for a in entrada.analise.afirmacoes if a.id in aprovadas for i in a.evidencias_ids}
    evidencias = [e for e in entrada.pesquisa.evidencias if e.id in usadas]
    lista = [LIMITE_SUPORTE]
    if any(e.tipo == "financeira" for e in evidencias):
        lista.append(LIMITE_PADRAO)
    if any(e.tipo == "documental" for e in evidencias):
        lista.append(LIMITE_EDUCATIVO)
    if any(e.origem.sintetica for e in evidencias):
        lista.append(LIMITE_SINTETICO)
    if entrada.pesquisa.status == "parcial":
        lista.append(LIMITE_PARCIAL)
    if any(v.regra == "suporte_documental" and v.resultado == "alerta" for v in entrada.validacao.verificacoes):
        lista.append(LIMITE_ALERTA)
    return tuple(curto(item) for item in lista)


def prompt_redacao(entrada: EntradaComunicacao) -> str:
    """Prompt do redator. Leva só a pergunta e as afirmações aprovadas.

    Não leva evidências, dados de contexto nem afirmações bloqueadas: o
    redator não tem como citar fonte nem repetir o que a Validation barrou.
    """
    aprovadas = set(entrada.validacao.afirmacoes_aprovadas)
    afirmacoes = [{"id": a.id, "texto": a.texto} for a in entrada.analise.afirmacoes if a.id in aprovadas]
    return (
        "Reescreva as afirmações abaixo como uma resposta curta e clara em português do Brasil, "
        "dirigida à usuária. Use somente o conteúdo das afirmações: não acrescente fatos, números, "
        "conselhos nem fontes. Todas as afirmações devem aparecer. "
        'Responda só com JSON no formato {"paragrafos": [{"afirmacoes_ids": ["a1"], "texto": "..."}]}.\n'
        f"Pergunta: {entrada.pergunta}\n"
        f"Afirmações: {json.dumps(afirmacoes, ensure_ascii=False)}"
    )


def problemas_redacao(entrada: EntradaComunicacao, saida: SaidaComunicacao) -> list[str]:
    """Checagens 2 e 3 do módulo. Lista vazia quando a redação pode ser usada."""
    problemas = inconsistencias_comunicacao(entrada.analise, entrada.validacao, saida)
    por_id = {a.id: a.texto for a in entrada.analise.afirmacoes}
    for indice, paragrafo in enumerate(saida.paragrafos, start=1):
        referencia = " ".join(por_id.get(i, "") for i in paragrafo.afirmacoes_ids)
        fracao = palavras_novas(paragrafo.texto, referencia)
        if fracao > MAX_PALAVRAS_NOVAS:
            problemas.append(f"parágrafo {indice} traz {fracao:.0%} de palavras fora das afirmações")
    return problemas


class CommunicationAgent:
    """Chamável compatível com ``Agentes.communication``.

    ``redator`` é opcional. Qualquer erro dele (exceção, JSON inválido,
    redação reprovada nas checagens) faz a Communication usar o modelo; o
    motivo fica em ``ultimo_descarte`` para diagnóstico.
    """

    def __init__(self, redator: Redator | None = None):
        self.redator = redator
        self.ultimo_descarte: list[str] = []

    def __call__(self, entrada: EntradaComunicacao) -> SaidaComunicacao:
        self.ultimo_descarte = []
        limites_resposta = limites(entrada)
        if self.redator is not None:
            redigida = self._pelo_redator(entrada, limites_resposta)
            if redigida is not None:
                return redigida
        return SaidaComunicacao(paragrafos=redigir_por_modelo(entrada), limites=limites_resposta)

    def _pelo_redator(self, entrada: EntradaComunicacao, limites_resposta) -> SaidaComunicacao | None:
        try:
            bruto = json.loads(self.redator(prompt_redacao(entrada)))
            saida = SaidaComunicacao(paragrafos=bruto["paragrafos"], limites=limites_resposta)
        except (ValueError, TypeError, KeyError, ValidationError) as erro:
            self.ultimo_descarte = [f"redação inválida: {type(erro).__name__}"]
            return None
        except Exception as erro:  # noqa: BLE001 - falha do redator nunca derruba a resposta
            self.ultimo_descarte = [f"redator falhou: {type(erro).__name__}"]
            return None
        problemas = problemas_redacao(entrada, saida)
        if problemas:
            self.ultimo_descarte = problemas
            return None
        return saida
