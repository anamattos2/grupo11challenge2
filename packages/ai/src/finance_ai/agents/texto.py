"""Utilitários de texto determinísticos usados pela Validation e pela Communication.

Sem modelo: comparam palavras de conteúdo depois de normalizar caixa e acentos.
Servem como aproximação conferível de "o texto diz o mesmo que a fonte"; não
substituem revisão humana de pertinência.
"""

from __future__ import annotations

import re
import unicodedata

_PALAVRA = re.compile(r"[a-z]+")

# Palavras funcionais frequentes em português (já sem acento). Ficam fora da
# comparação porque não dizem nada sobre o conteúdo.
PALAVRAS_FUNCIONAIS = frozenset("""
a ao aos as com como da das de do dos e em entre era essa esse esta este eu foi
for ha isso isto ja la mais mas me mesmo muito na nao nas nem no nos o os ou para
pela pelas pelo pelos por pode podem quando que quem se sem ser seu sua seus suas
so sobre tambem tem ter um uma umas uns voce voces ate apos cada qual quais
""".split())


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos: 'Emergência' vira 'emergencia'."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(ch for ch in decomposto if not unicodedata.combining(ch))


def _radical(palavra: str) -> str:
    """Corte simples de plural e gênero.

    'despesas'/'despesa', 'essenciais'/'essencial' e 'imprevistos'/'imprevisto'
    chegam ao mesmo radical. Não é um stemmer: formas verbais continuam
    diferentes ('cobre' x 'cobrir').
    """
    if len(palavra) <= 4:
        return palavra
    if palavra.endswith(("ais", "eis")):
        palavra = palavra[:-2] + "l"
    elif palavra.endswith(("oes", "aes")):
        palavra = palavra[:-3]
    elif palavra.endswith("s"):
        palavra = palavra[:-1]
    if len(palavra) > 4 and palavra[-1] in "aoe":
        palavra = palavra[:-1]
    return palavra


def palavras_conteudo(texto: str) -> set[str]:
    """Radicais das palavras de conteúdo (3+ letras, fora das funcionais)."""
    return {
        _radical(p) for p in _PALAVRA.findall(normalizar(texto))
        if len(p) >= 3 and p not in PALAVRAS_FUNCIONAIS
    }


def cobertura(texto: str, referencia: str) -> float:
    """Fração das palavras de conteúdo de ``texto`` que aparecem em ``referencia``.

    1.0 quando ``texto`` não tem palavra de conteúdo (nada a conferir).
    """
    palavras = palavras_conteudo(texto)
    if not palavras:
        return 1.0
    return len(palavras & palavras_conteudo(referencia)) / len(palavras)


def curto(texto: str, limite: int = 300) -> str:
    """Corta para caber em ``TextoCurto`` sem quebrar no meio de forma silenciosa."""
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"
