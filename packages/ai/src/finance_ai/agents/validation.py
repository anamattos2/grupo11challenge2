"""Validation Agent (S4-04 / #78): confere a análise antes da comunicação.

Todas as regras são determinísticas e conferíveis; nenhuma usa LLM. Cada
afirmação passa pelas cinco regras do contrato (``RegraValidacao``) e cada
checagem vira uma ``Verificacao`` com resultado ``ok``, ``alerta`` ou ``falha``.

| Regra | Falha (bloqueia) | Alerta (não bloqueia) |
|---|---|---|
| ``referencias_existentes`` | evidência citada não está na pesquisa | fonte sintética, pesquisa parcial |
| ``natureza_compativel`` | dado pessoal/cálculo sem ``fin:``; orientação sem ``doc:`` | |
| ``numeros_conferem`` | número ausente das evidências citadas; valor atribuído ao campo errado (receitas x despesas) | |
| ``suporte_documental`` | orientação com pouca sobreposição com o trecho ou com a negação invertida | sobreposição parcial, score baixo |
| ``escopo_permitido`` | ativo específico, acesso bancário, escrita, evidência sem permissão (exceto quando negados) | |

Qualquer falha reprova a análise, lista as afirmações bloqueadas em
``alegacoes_sem_suporte`` e devolve feedback objetivo para uma revisão da
Analysis. Sem falha, todas as afirmações são aprovadas (com ou sem alertas).

Números da pergunta só são aceitos em orientação educativa: um valor que só a
pergunta traz nunca é confirmado como dado da usuária.

Limite conhecido: ``suporte_documental`` mede sobreposição de palavras e a
polaridade delas, não significado. Uma paráfrase fiel com outras palavras pode
virar alerta, e uma frase que reaproveita as palavras do trecho com sentido
diferente, sem negação explícita ("serve" x "não é indicada"), ainda pode passar.
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
from .fluxo import _NUMERO, _normalizar_numero, numeros
from .texto import cobertura, curto, negacao_antes, normalizar, sentido_invertido

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
    # "exclui" fica de fora: sem acento, é também o presente ("o orçamento
    # exclui gastos"). O passado "excluí" é conferido no texto original.
    ("promete ação de escrita", re.compile(
        r"\b(?:registrei|cadastrei|lancei|apaguei|transferi|movimentei|alterei)\b"
        r"|\bvou (?:registrar|cadastrar|lancar|apagar|excluir|transferir|alterar)\b")),
)
_EXCLUI_PASSADO = re.compile(r"\bexcluí\b")


def _problemas_de_escopo(texto: str) -> list[str]:
    """Padrões fora do escopo que aparecem afirmados.

    Uma ocorrência logo depois de uma negação ("nunca compartilhe sua senha",
    "não recomendo comprar ações") é orientação de segurança, não violação.
    """
    normalizado = normalizar(texto)
    problemas = [nome for nome, padrao in _FORA_DO_ESCOPO
                 if any(not negacao_antes(normalizado, m.start()) for m in padrao.finditer(normalizado))]
    if _EXCLUI_PASSADO.search(texto.lower()):
        problemas.append("promete ação de escrita")
    return list(dict.fromkeys(problemas))


# Termo do texto (já normalizado) -> campo de ``Evidencia.valores`` que ele nomeia.
# Os termos mais longos vêm antes para "saldo total" não ser lido como outro saldo.
_CAMPOS = (
    (r"saldo total", "saldo_total_declarado"),
    (r"saldo declarado", "saldo_declarado"),
    (r"receitas?", "receitas"),
    (r"receb(?:i|eu|emos|eram)", "receitas"),
    (r"despesas?", "despesas"),
    (r"gast[a-z]*", "despesas"),
    (r"resultado", "resultado"),
    (r"metas?", "meta"),
    (r"falta(?:m|va|vam)?", "falta"),
)
_TERMO_CAMPO = re.compile("|".join(rf"\b(?P<c{i}>{termo})\b" for i, (termo, _) in enumerate(_CAMPOS)))
_SINAL_NEGATIVO = re.compile(r"(?<![0-9])[-−]\s*(?:r\$\s*)?$|r\$\s*[-−]\s*$")
_LIGACAO_DEPOIS = re.compile(r"\s*(?:em|de)\s+(?:suas\s+|seus\s+)?")


def _campo_do_termo(m: re.Match[str]) -> str:
    return _CAMPOS[int(m.lastgroup[1:])][1]


def _campos_por_valor(evidencias: list[Evidencia]) -> tuple[dict[str, set[str]], set[str]]:
    """Valor canônico -> campos que têm esse valor, e os campos presentes."""
    por_valor: dict[str, set[str]] = {}
    presentes: set[str] = set()
    for evidencia in evidencias:
        if evidencia.tipo != "financeira":
            continue
        for campo, valor in evidencia.valores.items():
            if valor is None:
                continue
            presentes.add(campo)
            for numero in numeros(valor):
                if numero != "0" and valor.startswith("-"):
                    numero = f"-{numero}"
                por_valor.setdefault(numero, set()).add(campo)
    return por_valor, presentes


def _campo_ligado(normalizado: str, inicio: int, fim: int) -> str | None:
    """Campo que o texto associa ao número em ``[inicio, fim)``, se houver.

    Primeiro "R$ 1.850,40 em/de despesas", depois o termo mais próximo antes do
    número na mesma oração ("o resultado do mês foi R$ ..."). Vírgula com
    espaço encerra a oração; a vírgula decimal não tem espaço.
    """
    ligacao = _LIGACAO_DEPOIS.match(normalizado, fim)
    if ligacao:
        termo = _TERMO_CAMPO.match(normalizado, ligacao.end())
        if termo:
            return _campo_do_termo(termo)
    oracao = re.split(r"\.(?![0-9])|[;!?]|,\s", normalizado[:inicio])[-1]
    termos = list(_TERMO_CAMPO.finditer(oracao))
    return _campo_do_termo(termos[-1]) if termos else None


def _valores_trocados(texto: str, evidencias: list[Evidencia]) -> list[str]:
    """Números que existem nas evidências, mas em outro campo do que o texto diz.

    Só confere números que são valores das evidências citadas e campos que
    essas evidências têm; datas, anos e números sem campo nomeado ficam com
    ``numeros_conferem``.
    """
    por_valor, presentes = _campos_por_valor(evidencias)
    normalizado = normalizar(texto)
    trocados = []
    for m in _NUMERO.finditer(normalizado):
        numero = _normalizar_numero(m.group())
        if numero != "0" and _SINAL_NEGATIVO.search(normalizado[:m.start()]):
            numero = f"-{numero}"
        campo = _campo_ligado(normalizado, m.start(), m.end())
        magnitude = numero.lstrip("-")
        if (campo in presentes and (magnitude in por_valor or f"-{magnitude}" in por_valor)
                and campo not in por_valor.get(numero, set())):
            trocados.append(f"{m.group()} não é o valor de {campo}")
    return trocados

_PERMISSAO_POR_TIPO = {"financeira": Permissao.FINANCEIRO_LER, "documental": Permissao.DOCUMENTOS_LER}

# Quando há mais de um motivo, o mais grave vira ``motivo_bloqueio``.
_PRIORIDADE = (
    MotivoBloqueio.REFERENCIA_INEXISTENTE,
    MotivoBloqueio.FORA_DO_ESCOPO,
    MotivoBloqueio.NUMERO_DIVERGENTE,
    MotivoBloqueio.SEM_SUPORTE,
)


def _numeros_permitidos(evidencias: list[Evidencia], pergunta: str, natureza: str) -> set[str]:
    """Números que uma afirmação pode repetir: os das evidências citadas.

    Os da pergunta só valem para orientação educativa ("o que é a regra
    50-30-20?"). Num dado pessoal ou cálculo, um valor que só a pergunta traz
    ("gastei R$ 3.000?") não pode ser confirmado como registro da usuária.
    """
    permitidos = numeros(pergunta) if natureza == "orientacao_educativa" else set()
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
        divergentes = sorted(numeros(afirmacao.texto)
                             - _numeros_permitidos(citadas, entrada.pergunta, afirmacao.natureza))
        trocados = _valores_trocados(afirmacao.texto, citadas)
        if divergentes:
            registrar(RegraValidacao.NUMEROS_CONFEREM, "falha",
                      f"números que não estão nas evidências citadas: {', '.join(divergentes)}",
                      aid, MotivoBloqueio.NUMERO_DIVERGENTE)
        if trocados:
            registrar(RegraValidacao.NUMEROS_CONFEREM, "falha",
                      f"valores atribuídos ao campo errado: {'; '.join(trocados)}",
                      aid, MotivoBloqueio.NUMERO_DIVERGENTE)
        if not divergentes and not trocados:
            registrar(RegraValidacao.NUMEROS_CONFEREM, "ok", "números conferem com as evidências", aid)

        # suporte_documental (só para orientação, que é o que vem de documento)
        documentais = [e for e in citadas if e.tipo == "documental"]
        if afirmacao.natureza == "orientacao_educativa" and documentais:
            trechos = " ".join(e.trecho for e in documentais)
            fracao = cobertura(afirmacao.texto, trechos)
            score = max(e.score for e in documentais)
            invertidas = sentido_invertido(afirmacao.texto, trechos)
            if invertidas:
                registrar(RegraValidacao.SUPORTE_DOCUMENTAL, "falha",
                          "a orientação inverte o sentido do trecho citado "
                          f"(negação em: {', '.join(invertidas)})", aid, MotivoBloqueio.SEM_SUPORTE)
            elif fracao < COBERTURA_MINIMA:
                registrar(RegraValidacao.SUPORTE_DOCUMENTAL, "falha",
                          f"o trecho citado não sustenta a orientação (cobertura {fracao:.2f})",
                          aid, MotivoBloqueio.SEM_SUPORTE)
            elif fracao < COBERTURA_ALERTA or score < SCORE_ALERTA:
                registrar(RegraValidacao.SUPORTE_DOCUMENTAL, "alerta",
                          f"suporte parcial (cobertura {fracao:.2f}, score {score:.2f})", aid)
            else:
                registrar(RegraValidacao.SUPORTE_DOCUMENTAL, "ok", f"cobertura {fracao:.2f}", aid)

        # escopo_permitido
        problemas_escopo = _problemas_de_escopo(afirmacao.texto)
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
