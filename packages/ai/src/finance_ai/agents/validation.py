"""Validation Agent (S4-04 / #78): confere a análise antes da comunicação.

Todas as regras são determinísticas e conferíveis; nenhuma usa LLM. Cada
afirmação passa pelas cinco regras do contrato (``RegraValidacao``) e cada
checagem vira uma ``Verificacao`` com resultado ``ok``, ``alerta`` ou ``falha``.

| Regra | Falha (bloqueia) | Alerta (não bloqueia) |
|---|---|---|
| ``referencias_existentes`` | evidência citada não está na pesquisa | fonte sintética, pesquisa parcial |
| ``natureza_compativel`` | dado pessoal/cálculo sem ``fin:``; orientação sem ``doc:`` | |
| ``numeros_conferem`` | número da afirmação ausente das evidências citadas | |
| ``suporte_documental`` | orientação com pouca sobreposição com o trecho | sobreposição parcial, score baixo |
| ``escopo_permitido`` | ativo específico, acesso bancário, escrita, evidência sem permissão | |

Qualquer falha reprova a análise, lista as afirmações bloqueadas em
``alegacoes_sem_suporte`` e devolve feedback objetivo para uma revisão da
Analysis. Sem falha, todas as afirmações são aprovadas (com ou sem alertas).

Limite conhecido: ``suporte_documental`` mede sobreposição de palavras, não
significado. Uma paráfrase fiel com outras palavras pode virar alerta, e uma
frase que reaproveita as palavras do trecho com sentido diferente pode passar.
"""

from __future__ import annotations

import re

from .contratos import (
    EntradaValidacao,
    Evidencia,
    MotivoBloqueio,
    Permissao,
    RegraValidacao,
    SaidaValidacao,
    Verificacao,
)
from .fluxo import numeros
from .texto import cobertura, curto, normalizar

COBERTURA_MINIMA = 0.5
"""Abaixo disso, a orientação não é sustentada pelo trecho citado (falha)."""

COBERTURA_ALERTA = 0.75
"""Entre o mínimo e este valor, a orientação passa com alerta."""

SCORE_ALERTA = 0.85
"""Trecho recuperado com similaridade abaixo disso gera alerta."""

# Padrões aplicados ao texto normalizado (minúsculas, sem acentos).
_FORA_DO_ESCOPO: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("recomenda ativo específico", re.compile(r"\b[a-z]{4}(?:3|4|5|6|11)\b")),
    ("recomenda ativo específico", re.compile(
        r"\b(?:compre|comprar|invista|investir|aplique|aplicar|recomendo)\b"
        r".{0,40}\b(?:acoes?|fundos?|cdbs?|lcis?|lcas?|tesouro|bitcoin|cripto\w*|debentures?|fiis?)\b")),
    ("menciona acesso bancário", re.compile(
        r"\b(?:senha|token|open finance|login do banco|internet banking)\b"
        r"|\b(?:acesse|acessar|conecte|conectar)\b.{0,20}\bconta (?:bancaria|do banco)\b")),
    ("promete ação de escrita", re.compile(
        r"\b(?:registrei|cadastrei|lancei|apaguei|exclui|transferi|movimentei|alterei)\b"
        r"|\bvou (?:registrar|cadastrar|lancar|apagar|excluir|transferir|alterar)\b")),
)

_PERMISSAO_POR_TIPO = {"financeira": Permissao.FINANCEIRO_LER, "documental": Permissao.DOCUMENTOS_LER}

# Quando há mais de um motivo, o mais grave vira ``motivo_bloqueio``.
_PRIORIDADE = (
    MotivoBloqueio.REFERENCIA_INEXISTENTE,
    MotivoBloqueio.FORA_DO_ESCOPO,
    MotivoBloqueio.NUMERO_DIVERGENTE,
    MotivoBloqueio.SEM_SUPORTE,
)


def _numeros_permitidos(evidencias: list[Evidencia], pergunta: str) -> set[str]:
    """Números que uma afirmação pode repetir: os das evidências e os da pergunta."""
    permitidos = numeros(pergunta)
    for evidencia in evidencias:
        if evidencia.tipo == "financeira":
            permitidos |= numeros(evidencia.resumo)
            for valor in evidencia.valores.values():
                if valor is not None:
                    permitidos |= numeros(valor)
            for data in (evidencia.localizacao.periodo_inicio, evidencia.localizacao.periodo_fim):
                if data is not None:
                    permitidos |= numeros(data.isoformat()) | numeros(data.strftime("%d/%m/%Y"))
        else:
            permitidos |= numeros(evidencia.trecho)
    return permitidos


class ValidationAgent:
    """Chamável compatível com ``Agentes.validation``."""

    def __call__(self, entrada: EntradaValidacao) -> SaidaValidacao:
        return validar(entrada)


def validar(entrada: EntradaValidacao) -> SaidaValidacao:
    pesquisa, analise = entrada.pesquisa, entrada.analise
    evidencias = {e.id: e for e in pesquisa.evidencias}
    permissoes = set(entrada.contexto.permissoes)
    verificacoes: list[Verificacao] = []
    bloqueios: dict[str, list[MotivoBloqueio]] = {}
    feedback: list[str] = []

    def registrar(regra, resultado, detalhe, afirmacao_id=None, motivo=None):
        verificacoes.append(Verificacao(regra=regra, resultado=resultado,
                                        afirmacao_id=afirmacao_id, detalhe=curto(detalhe)))
        if resultado == "falha":
            bloqueios.setdefault(afirmacao_id, []).append(motivo)
            feedback.append(curto(f"{afirmacao_id}: {detalhe}"))

    if pesquisa.status == "parcial":
        registrar(RegraValidacao.REFERENCIAS_EXISTENTES, "alerta",
                  "pesquisa parcial: alguma fonte foi negada ou falhou")

    for afirmacao in analise.afirmacoes:
        aid = afirmacao.id
        faltando = [i for i in afirmacao.evidencias_ids if i not in evidencias]
        if faltando:
            registrar(RegraValidacao.REFERENCIAS_EXISTENTES, "falha",
                      f"cita evidências que não estão na pesquisa: {', '.join(faltando)}",
                      aid, MotivoBloqueio.REFERENCIA_INEXISTENTE)
            continue  # sem as evidências, as outras regras não têm o que conferir
        citadas = [evidencias[i] for i in afirmacao.evidencias_ids]
        sinteticas = [e.id for e in citadas if e.origem.sintetica]
        if sinteticas:
            registrar(RegraValidacao.REFERENCIAS_EXISTENTES, "alerta",
                      f"usa fonte sintética (dados de demonstração): {', '.join(sinteticas)}", aid)
        else:
            registrar(RegraValidacao.REFERENCIAS_EXISTENTES, "ok", "todas as evidências existem", aid)

        # natureza_compativel
        tipos = {e.tipo for e in citadas}
        exige = "documental" if afirmacao.natureza == "orientacao_educativa" else "financeira"
        if exige in tipos:
            registrar(RegraValidacao.NATUREZA_COMPATIVEL, "ok", f"{afirmacao.natureza} com evidência {exige}", aid)
        else:
            registrar(RegraValidacao.NATUREZA_COMPATIVEL, "falha",
                      f"{afirmacao.natureza} precisa de evidência {exige}", aid, MotivoBloqueio.SEM_SUPORTE)

        # numeros_conferem
        divergentes = sorted(numeros(afirmacao.texto) - _numeros_permitidos(citadas, entrada.pergunta))
        if divergentes:
            registrar(RegraValidacao.NUMEROS_CONFEREM, "falha",
                      f"números que não estão nas evidências citadas: {', '.join(divergentes)}",
                      aid, MotivoBloqueio.NUMERO_DIVERGENTE)
        else:
            registrar(RegraValidacao.NUMEROS_CONFEREM, "ok", "números conferem com as evidências", aid)

        # suporte_documental (só para orientação, que é o que vem de documento)
        documentais = [e for e in citadas if e.tipo == "documental"]
        if afirmacao.natureza == "orientacao_educativa" and documentais:
            fracao = cobertura(afirmacao.texto, " ".join(e.trecho for e in documentais))
            score = max(e.score for e in documentais)
            if fracao < COBERTURA_MINIMA:
                registrar(RegraValidacao.SUPORTE_DOCUMENTAL, "falha",
                          f"o trecho citado não sustenta a orientação (cobertura {fracao:.2f})",
                          aid, MotivoBloqueio.SEM_SUPORTE)
            elif fracao < COBERTURA_ALERTA or score < SCORE_ALERTA:
                registrar(RegraValidacao.SUPORTE_DOCUMENTAL, "alerta",
                          f"suporte parcial (cobertura {fracao:.2f}, score {score:.2f})", aid)
            else:
                registrar(RegraValidacao.SUPORTE_DOCUMENTAL, "ok", f"cobertura {fracao:.2f}", aid)

        # escopo_permitido
        problemas_escopo = [nome for nome, padrao in _FORA_DO_ESCOPO
                            if padrao.search(normalizar(afirmacao.texto))]
        sem_permissao = sorted({e.id for e in citadas if _PERMISSAO_POR_TIPO[e.tipo] not in permissoes})
        if sem_permissao:
            problemas_escopo.append(f"usa evidência sem permissão no contexto: {', '.join(sem_permissao)}")
        if problemas_escopo:
            registrar(RegraValidacao.ESCOPO_PERMITIDO, "falha", "; ".join(dict.fromkeys(problemas_escopo)),
                      aid, MotivoBloqueio.FORA_DO_ESCOPO)
        else:
            registrar(RegraValidacao.ESCOPO_PERMITIDO, "ok", "dentro do escopo autorizado", aid)

    if bloqueios:
        motivos = {m for lista in bloqueios.values() for m in lista}
        return SaidaValidacao(
            decisao="reprovada",
            verificacoes=verificacoes,
            alegacoes_sem_suporte=tuple(a for a in (x.id for x in analise.afirmacoes) if a in bloqueios),
            motivo_bloqueio=next(m for m in _PRIORIDADE if m in motivos),
            feedback=tuple(dict.fromkeys(feedback)),
        )
    tem_alerta = any(v.resultado == "alerta" for v in verificacoes)
    return SaidaValidacao(
        decisao="aprovada_com_alertas" if tem_alerta else "aprovada",
        verificacoes=verificacoes,
        afirmacoes_aprovadas=tuple(a.id for a in analise.afirmacoes),
    )
