"""Redação das afirmações da Analysis com números só por referência (S4-03 / #77).

Quem redige uma afirmação (as regras ou um LLM) **não escreve números de dados
financeiros**. Ele escreve um marcador que aponta para um valor que o backend
já calculou::

    "Em {{fin:resumo_transacoes:cad0c2b2ac81|periodo}} você registrou
     {{fin:resumo_transacoes:cad0c2b2ac81|despesas}} em despesas essenciais."

``materializar`` troca cada marcador pelo valor da evidência, já formatado
(``outubro de 2026``, ``R$ 1.850,40``), e recusa o rascunho se:

- o marcador aponta para evidência ou chave que não existe, ou para valor nulo;
- sobra algum algarismo fora dos marcadores numa afirmação sobre dados
  pessoais (seria um número digitado pelo redator, ou seja, aritmética livre);
- uma orientação educativa traz número que não está no trecho citado;
- a natureza não combina com as evidências (dado pessoal sem evidência
  financeira, orientação educativa citando dado financeiro).

É a mesma ideia de *structured generation* com referências: o modelo escolhe
o que dizer; os números saem do sistema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import re
from typing import Iterable

from .contratos import Afirmacao, EvidenciaDocumental, EvidenciaFinanceira, SaidaPesquisa
from .fluxo import numeros

MARCADOR = re.compile(r"\{\{\s*(fin:[a-z_]{3,40}:[0-9a-f]{12})\s*\|\s*([a-z][a-z0-9_]{1,39})\s*\}\}")
_ALGARISMO = re.compile(r"\d")

CHAVES_DERIVADAS = frozenset({"resultado", "saldo_total_declarado", "falta", "progresso_percentual", "meta"})
"""Valores que o backend obtém por conta (soma, diferença, percentual).

Uma afirmação que usa um deles tem natureza ``calculo``: o número é resultado
de um cálculo, mas de um cálculo feito pela ferramenta, não pela Analysis.
"""

NATUREZAS = ("dado_pessoal", "calculo", "orientacao_educativa")

_NOMES_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                "agosto", "setembro", "outubro", "novembro", "dezembro")


class ErroRedacao(ValueError):
    """Rascunho recusado; a mensagem diz o motivo (vai para o diagnóstico)."""


@dataclass(frozen=True)
class Rascunho:
    natureza: str
    texto: str
    evidencias_ids: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Formatação (sem aritmética: só muda a aparência do texto do backend)
# --------------------------------------------------------------------------


def formatar_brl(bruto: str) -> str:
    """``"1850.40"`` → ``"R$ 1.850,40"``; ``"-20.00"`` → ``"-R$ 20,00"``."""
    sinal, digitos = ("-", bruto[1:]) if bruto.startswith("-") else ("", bruto)
    inteiro, centavos = digitos.split(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return f"{sinal}R$ {'.'.join(grupos)},{centavos}"


def formatar_valor(chave: str, bruto: str) -> str:
    if chave.endswith("_percentual"):
        return f"{bruto.replace('.', ',')}%"
    return formatar_brl(bruto)


def _mes_inteiro(inicio: date, fim: date) -> bool:
    proximo = date(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)
    return inicio.day == 1 and fim == proximo - timedelta(days=1)


def rotulo_periodo(inicio: date | None, fim: date | None) -> str | None:
    if not inicio or not fim:
        return None
    if _mes_inteiro(inicio, fim):
        return f"{_NOMES_MESES[inicio.month - 1]} de {inicio.year}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


# --------------------------------------------------------------------------
# Números permitidos por evidência
# --------------------------------------------------------------------------


def numeros_da_evidencia(evidencia) -> set[str]:
    """Números que uma afirmação pode conter por citar esta evidência.

    Financeira: os valores (com e sem sinal) e as partes das datas do período.
    Documental: os números do próprio trecho (ex.: "50-30-20").
    """
    if isinstance(evidencia, EvidenciaDocumental):
        return numeros(evidencia.trecho)
    permitidos: set[str] = set()
    for bruto in evidencia.valores.values():
        if bruto is not None:
            permitidos |= numeros(bruto.lstrip("-"))
    for dia in (evidencia.localizacao.periodo_inicio, evidencia.localizacao.periodo_fim):
        if dia:
            permitidos |= {str(dia.year), str(dia.month), str(dia.day)}
    return permitidos


def numeros_sem_origem(afirmacao: Afirmacao, pesquisa: SaidaPesquisa) -> set[str]:
    """Números do texto que não estão em nenhuma evidência citada.

    É a regra ``numeros_conferem`` da Validation; a Analysis a aplica antes,
    em si mesma, e os testes a aplicam em toda saída.
    """
    por_id = {e.id: e for e in pesquisa.evidencias}
    permitidos: set[str] = set()
    for evidencia_id in afirmacao.evidencias_ids:
        if evidencia_id in por_id:
            permitidos |= numeros_da_evidencia(por_id[evidencia_id])
    return numeros(afirmacao.texto) - permitidos


# --------------------------------------------------------------------------
# Materialização
# --------------------------------------------------------------------------


def _valor_do_marcador(evidencia: EvidenciaFinanceira, chave: str) -> str:
    if chave == "periodo":
        rotulo = rotulo_periodo(evidencia.localizacao.periodo_inicio, evidencia.localizacao.periodo_fim)
        if rotulo is None:
            raise ErroRedacao(f"a evidência {evidencia.id} não tem período")
        return rotulo
    if chave not in evidencia.valores:
        raise ErroRedacao(f"a evidência {evidencia.id} não tem o valor '{chave}'")
    bruto = evidencia.valores[chave]
    if bruto is None:
        raise ErroRedacao(f"o valor '{chave}' da evidência {evidencia.id} não foi calculado pelo backend")
    return formatar_valor(chave, bruto)


def materializar(rascunho: Rascunho, pesquisa: SaidaPesquisa, afirmacao_id: str) -> Afirmacao:
    """Transforma um rascunho em ``Afirmacao`` ou lança ``ErroRedacao``."""
    if rascunho.natureza not in NATUREZAS:
        raise ErroRedacao(f"natureza desconhecida: {rascunho.natureza}")
    por_id = {e.id: e for e in pesquisa.evidencias}

    usados: list[tuple[str, str]] = []

    def trocar(encontro: re.Match) -> str:
        evidencia_id, chave = encontro.group(1), encontro.group(2)
        evidencia = por_id.get(evidencia_id)
        if not isinstance(evidencia, EvidenciaFinanceira):
            raise ErroRedacao(f"marcador aponta para a evidência {evidencia_id}, que não está na pesquisa")
        usados.append((evidencia_id, chave))
        return _valor_do_marcador(evidencia, chave)

    texto = MARCADOR.sub(trocar, rascunho.texto)
    resto = MARCADOR.sub("", rascunho.texto)
    if "{{" in resto or "}}" in resto:
        raise ErroRedacao("marcador malformado")

    ids = list(dict.fromkeys([*rascunho.evidencias_ids, *(i for i, _ in usados)]))
    faltando = [i for i in ids if i not in por_id]
    if faltando:
        raise ErroRedacao(f"cita evidências que não estão na pesquisa: {faltando}")
    if not ids:
        raise ErroRedacao("afirmação sem evidência")
    financeiras = [i for i in ids if isinstance(por_id[i], EvidenciaFinanceira)]
    documentais = [i for i in ids if isinstance(por_id[i], EvidenciaDocumental)]

    if rascunho.natureza == "orientacao_educativa":
        if financeiras:
            raise ErroRedacao("orientação educativa não cita dado financeiro da usuária")
        extras = numeros(resto) - set().union(*(numeros(por_id[i].trecho) for i in documentais))
        if extras:
            raise ErroRedacao(f"orientação educativa com números fora do trecho: {sorted(extras)}")
        natureza = "orientacao_educativa"
    else:
        if not financeiras:
            raise ErroRedacao("afirmação sobre dados pessoais exige evidência financeira")
        if _ALGARISMO.search(resto):
            raise ErroRedacao("número escrito fora de marcador: valores só vêm das ferramentas")
        derivado = any(chave in CHAVES_DERIVADAS for _, chave in usados)
        natureza = "calculo" if derivado or rascunho.natureza == "calculo" else "dado_pessoal"

    texto = re.sub(r"\s+", " ", texto).strip()
    if not texto or len(texto) > 600:
        raise ErroRedacao("texto vazio ou longo demais")
    afirmacao = Afirmacao(id=afirmacao_id, texto=texto, natureza=natureza, evidencias_ids=ids)
    sem_origem = numeros_sem_origem(afirmacao, pesquisa)
    if sem_origem:  # defesa em profundidade: não deveria acontecer depois das regras acima
        raise ErroRedacao(f"números sem origem: {sorted(sem_origem)}")
    return afirmacao


def materializar_todos(rascunhos: Iterable[Rascunho], pesquisa: SaidaPesquisa,
                       maximo: int = 5) -> tuple[list[Afirmacao], list[str]]:
    """Devolve (afirmações, recusas).

    O id vem da posição do rascunho (``a1`` é sempre o primeiro rascunho), e
    não da contagem dos que passaram: um rascunho recusado deixa um buraco na
    numeração, mas não muda o id dos outros.
    """
    afirmacoes, recusas = [], []
    textos: set[str] = set()
    for indice, rascunho in enumerate(rascunhos):
        if len(afirmacoes) >= maximo:
            recusas.append("limite de afirmações atingido")
            break
        try:
            afirmacao = materializar(rascunho, pesquisa, f"a{indice + 1}")
        except ErroRedacao as erro:
            recusas.append(str(erro))
            continue
        if afirmacao.texto in textos:
            continue
        textos.add(afirmacao.texto)
        afirmacoes.append(afirmacao)
    return afirmacoes, recusas


def comparar(a: str, b: str) -> str:
    """Comparação de dois valores do backend, feita pelo código (nunca pelo LLM)."""
    x, y = Decimal(a), Decimal(b)
    return "maiores" if x > y else "menores" if x < y else "iguais"
