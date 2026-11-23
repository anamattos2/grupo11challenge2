"""Do texto lido aos campos valor, data e estabelecimento, sem inventar.

Regra de ouro: um campo só fica ``presente`` quando existe exatamente uma
leitura plausível no texto, e o ``trecho`` que a sustenta é copiado do texto
lido. Se houver mais de uma opção, ou a única opção não tiver rótulo, ou a
leitura tiver baixa confiança, o campo fica ``ambiguo`` e as opções vão para a
usuária. O código nunca completa, corrige ou estima um valor.
"""
from __future__ import annotations

from datetime import date
import re
import unicodedata

from .contrato import Campo, CamposExtraidos
from .ocr import Leitura, Linha

CONFIANCA_MINIMA = 60.0  # abaixo disso (0–100), a leitura do Tesseract vira "ambígua"
MINIMO_CARACTERES_LEGIVEIS = 15

_DINHEIRO = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?![\d,])")
_DINHEIRO_PONTO = re.compile(r"(?<![\d,.])(\d+\.\d{2})(?![\d.])")  # "19.40", só em linha de total
_DATA = re.compile(r"(?<!\d)(\d{2})[/.\-](\d{2})[/.\-](\d{4}|\d{2})(?!\d)")
_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")

_TOTAL = re.compile(r"\b(valor\s+total|total\s+a\s+pagar|valor\s+a\s+pagar|total\s+geral|total)\b")
_NAO_E_TOTAL = re.compile(r"\b(subtotal|sub\s+total|itens|qtd|quantidade|troco|desconto|tributos|impostos|"
                          r"aprox|lei\s+12\.?741|recebido|dinheiro|pago)\b")
_ROTULO_LOJA = re.compile(r"^(estabelecimento|loja|empresa|razao\s+social)\s*[:\-]\s*(.+)$")
_NAO_E_LOJA = re.compile(r"\b(cupom|fiscal|nfc|nf-?e|documento|auxiliar|extrato|cnpj|cpf|inscricao|ie|im|"
                         r"rua|av|avenida|alameda|rodovia|travessa|bairro|cep|tel|telefone|fone|sat|"
                         r"consumidor|item|codigo|descricao|qtd|valor|total|data|hora|via|comprovante|"
                         r"venda|pagamento|cartao|credito|debito|pix)\b")


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def _decimal_de(texto: str) -> str:
    """'1.234,56' → '1234.56'. Só muda a notação; não arredonda nem corrige."""
    if "," in texto:
        return texto.replace(".", "").replace(",", ".")
    return texto


def _baixa_confianca(linha: Linha) -> bool:
    return 0 <= linha.confianca < CONFIANCA_MINIMA


# --------------------------------------------------------------------------
# Valor total
# --------------------------------------------------------------------------


def extrair_valor_total(leitura: Leitura) -> Campo:
    nos_totais: dict[str, Linha] = {}
    em_qualquer_linha: list[str] = []
    for linha in leitura.linhas:
        normal = _sem_acento(linha.texto)
        valores = [_decimal_de(v) for v in _DINHEIRO.findall(linha.texto)]
        if _TOTAL.search(normal) and not _NAO_E_TOTAL.search(normal):
            valores = valores or [_decimal_de(v) for v in _DINHEIRO_PONTO.findall(linha.texto)]
            for valor in valores:
                nos_totais.setdefault(valor, linha)
        em_qualquer_linha += [v for v in valores if v not in em_qualquer_linha]

    positivos = {v: l for v, l in nos_totais.items() if float(v) > 0}
    if len(positivos) == 1:
        (valor, linha), = positivos.items()
        if _baixa_confianca(linha):
            return Campo(estado="ambiguo", candidatos=[valor], motivo="leitura do total com baixa confiança")
        return Campo(estado="presente", valor=valor, trecho=linha.texto.strip()[:200])
    if len(positivos) > 1:
        return Campo(estado="ambiguo", candidatos=sorted(positivos)[:5],
                     motivo="mais de um valor em linhas de total")
    if em_qualquer_linha:
        return Campo(estado="ambiguo", candidatos=em_qualquer_linha[:5],
                     motivo="há valores, mas nenhum rotulado como total")
    return Campo(estado="ausente")


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------


def extrair_data(leitura: Leitura, hoje: date) -> Campo:
    validas: dict[str, Linha] = {}
    invalidas: list[str] = []
    for linha in leitura.linhas:
        for dia, mes, ano in _DATA.findall(linha.texto):
            ano_completo = int(ano) + 2000 if len(ano) == 2 else int(ano)
            bruto = f"{dia}/{mes}/{ano}"
            try:
                lida = date(ano_completo, int(mes), int(dia))
            except ValueError:
                invalidas.append(bruto)
                continue
            if lida > hoje or lida.year < 2000:
                invalidas.append(bruto)
                continue
            validas.setdefault(lida.isoformat(), linha)

    if len(validas) == 1:
        (valor, linha), = validas.items()
        if _baixa_confianca(linha):
            return Campo(estado="ambiguo", candidatos=[valor], motivo="leitura da data com baixa confiança")
        return Campo(estado="presente", valor=valor, trecho=linha.texto.strip()[:200])
    if len(validas) > 1:
        return Campo(estado="ambiguo", candidatos=sorted(validas)[:5], motivo="mais de uma data no comprovante")
    if invalidas:
        return Campo(estado="ambiguo", candidatos=invalidas[:5], motivo="data lida é impossível ou futura")
    return Campo(estado="ausente")


# --------------------------------------------------------------------------
# Estabelecimento
# --------------------------------------------------------------------------


def _parece_nome(texto: str) -> bool:
    normal = _sem_acento(texto)
    letras = sum(c.isalpha() for c in texto)
    return (letras >= 3 and letras / max(1, len(texto.replace(" ", ""))) >= 0.7
            and not _NAO_E_LOJA.search(normal) and not _DINHEIRO.search(texto) and not _DATA.search(texto))


def extrair_estabelecimento(leitura: Leitura) -> Campo:
    # 1) rótulo explícito ("Estabelecimento: ...")
    for linha in leitura.linhas:
        encontrado = _ROTULO_LOJA.match(_sem_acento(linha.texto).strip())
        if encontrado:
            inicio = len(linha.texto.strip()) - len(encontrado.group(2))
            nome = linha.texto.strip()[inicio:].strip(" .:-")
            if _parece_nome(nome):
                if _baixa_confianca(linha):
                    return Campo(estado="ambiguo", candidatos=[nome[:120]], motivo="leitura do nome com baixa confiança")
                return Campo(estado="presente", valor=nome[:120], trecho=linha.texto.strip()[:200])

    # 2) cabeçalho: linhas antes do CNPJ, da data, de valores ou dos itens
    cabecalho = []
    for linha in leitura.linhas:
        normal = _sem_acento(linha.texto)
        if (_CNPJ.search(linha.texto) or _DATA.search(linha.texto) or _DINHEIRO.search(linha.texto)
                or re.search(r"\b(item|codigo|descricao|cupom|nfc|cnpj)\b", normal)):
            break
        cabecalho.append(linha)
    nomes = [l for l in cabecalho if _parece_nome(l.texto.strip())]
    if not nomes:
        return Campo(estado="ausente")
    primeira = nomes[0]
    nome = re.sub(r"\s+", " ", primeira.texto).strip(" .:-")[:120]
    if _baixa_confianca(primeira):
        return Campo(estado="ambiguo", candidatos=[l.texto.strip()[:120] for l in nomes[:5]],
                     motivo="leitura do nome com baixa confiança")
    return Campo(estado="presente", valor=nome, trecho=primeira.texto.strip()[:200])


# --------------------------------------------------------------------------
# Tudo junto
# --------------------------------------------------------------------------


def legivel(leitura: Leitura) -> bool:
    caracteres = sum(c.isalnum() for c in leitura.texto)
    media = leitura.confianca_media
    return caracteres >= MINIMO_CARACTERES_LEGIVEIS and (media < 0 or media >= 30)


def interpretar(leitura: Leitura, hoje: date) -> tuple[str, CamposExtraidos]:
    if not legivel(leitura):
        ilegivel = Campo(estado="ausente", motivo="imagem ilegível")
        return "ilegivel", CamposExtraidos(valor_total=ilegivel, data=ilegivel, estabelecimento=ilegivel)
    campos = CamposExtraidos(valor_total=extrair_valor_total(leitura), data=extrair_data(leitura, hoje),
                             estabelecimento=extrair_estabelecimento(leitura))
    completos = all(c.estado == "presente" for c in (campos.valor_total, campos.data, campos.estabelecimento))
    return ("completa" if completos else "parcial"), campos
