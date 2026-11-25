"""Do texto lido aos campos valor, data e estabelecimento, sem inventar.

Regra de ouro: um campo só fica ``presente`` quando existe exatamente uma
leitura plausível no texto, e o ``trecho`` que a sustenta é copiado do texto
lido. Se houver mais de uma opção, ou a única opção não tiver rótulo, ou a
leitura tiver baixa confiança, o campo fica ``ambiguo`` e as opções vão para a
usuária. O código nunca completa, corrige ou estima um valor.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
import unicodedata

from .contrato import Campo, CamposExtraidos
from .ocr import Leitura, Linha

CONFIANCA_MINIMA = 60.0  # abaixo disso (0–100), a leitura do Tesseract vira "ambígua"
MINIMO_CARACTERES_LEGIVEIS = 15

_DINHEIRO = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?![\d,])")
_DINHEIRO_PONTO = re.compile(r"(?<![\d,.])(\d+\.\d{2})(?![\d.])")  # "19.40", só em linha de total
_SINAL_NEGATIVO = re.compile(r"[-−]\s*(?:r\$\s*)?$", re.IGNORECASE)
_ABRE_VALOR = re.compile(r"\(\s*(?:r\$\s*)?$", re.IGNORECASE)
_DATA_COMPRA = re.compile(r"\b(?:compra|venda|pagamento|transacao)\b")
_DATA_AUXILIAR = re.compile(r"\b(?:impressao|reimpressao|validade|vencimento)\b")
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


def _valores_da_linha(texto: str, padrao: re.Pattern[str]) -> list[str]:
    valores = []
    for numero in padrao.finditer(texto):
        anterior = texto[:numero.start()]
        posterior = texto[numero.end():]
        negativo = (_SINAL_NEGATIVO.search(anterior)
                    or (_ABRE_VALOR.search(anterior) and posterior.lstrip().startswith(")")))
        valor = _decimal_de(numero.group())
        valores.append(f"-{valor}" if negativo else valor)
    return valores


def extrair_valor_total(leitura: Leitura) -> Campo:
    nos_totais: dict[str, Linha] = {}
    em_qualquer_linha: list[str] = []
    for linha in leitura.linhas:
        normal = _sem_acento(linha.texto)
        valores = _valores_da_linha(linha.texto, _DINHEIRO)
        if _TOTAL.search(normal) and not _NAO_E_TOTAL.search(normal):
            valores.extend(_valores_da_linha(linha.texto, _DINHEIRO_PONTO))
            for valor in valores:
                nos_totais.setdefault(valor, linha)
        em_qualquer_linha += [v for v in valores if v not in em_qualquer_linha]

    if any(Decimal(valor) <= 0 for valor in nos_totais):
        return Campo(estado="ambiguo", candidatos=list(nos_totais)[:5],
                     motivo="há total zero ou negativo no comprovante")
    if len(nos_totais) == 1:
        (valor, linha), = nos_totais.items()
        if _baixa_confianca(linha):
            return Campo(estado="ambiguo", candidatos=[valor], motivo="leitura do total com baixa confiança")
        return Campo(estado="presente", valor=valor, trecho=linha.texto.strip()[:200])
    if len(nos_totais) > 1:
        return Campo(estado="ambiguo", candidatos=sorted(nos_totais)[:5],
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
    compras: list[tuple[Linha, re.Match[str]]] = []
    outras: list[tuple[Linha, re.Match[str]]] = []
    tem_auxiliares = False
    for linha in leitura.linhas:
        fim_anterior = 0
        for encontrada in _DATA.finditer(linha.texto):
            rotulo = _sem_acento(linha.texto[fim_anterior:encontrada.start()])
            fim_anterior = encontrada.end()
            if _DATA_AUXILIAR.search(rotulo):
                tem_auxiliares = True
            elif _DATA_COMPRA.search(rotulo):
                compras.append((linha, encontrada))
            else:
                outras.append((linha, encontrada))

    selecionadas = compras or outras
    if not selecionadas and tem_auxiliares:
        return Campo(estado="ambiguo", motivo="há apenas datas auxiliares no comprovante")

    for linha, encontrada in selecionadas:
        dia, mes, ano = encontrada.groups()
        ano_completo = int(ano) + 2000 if len(ano) == 2 else int(ano)
        bruto = encontrada.group()
        try:
            lida = date(ano_completo, int(mes), int(dia))
        except ValueError:
            invalidas.append(bruto)
            continue
        if lida > hoje or lida.year < 2000:
            invalidas.append(bruto)
            continue
        validas.setdefault(lida.isoformat(), linha)

    # Uma data válida sem rótulo e outra data auxiliar continuam ambíguas:
    # só o rótulo de compra permite resolver o papel de cada data.
    if not compras and tem_auxiliares and validas:
        return Campo(estado="ambiguo", candidatos=list(validas)[:5],
                     motivo="não foi possível distinguir a data da compra das datas auxiliares")
    if invalidas:
        return Campo(estado="ambiguo", candidatos=(list(validas) + invalidas)[:5],
                     motivo="data da compra impossível, futura ou conflitante")
    if len(validas) == 1:
        (valor, linha), = validas.items()
        if _baixa_confianca(linha):
            return Campo(estado="ambiguo", candidatos=[valor], motivo="leitura da data com baixa confiança")
        return Campo(estado="presente", valor=valor, trecho=linha.texto.strip()[:200])
    if len(validas) > 1:
        return Campo(estado="ambiguo", candidatos=sorted(validas)[:5], motivo="mais de uma data no comprovante")
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
    # 1) rótulos explícitos têm precedência sobre o cabeçalho.
    explicitos: dict[str, tuple[str, Linha]] = {}
    for linha in leitura.linhas:
        encontrado = _ROTULO_LOJA.match(_sem_acento(linha.texto).strip())
        if encontrado:
            inicio = len(linha.texto.strip()) - len(encontrado.group(2))
            nome = linha.texto.strip()[inicio:].strip(" .:-")
            if _parece_nome(nome):
                chave = " ".join(_sem_acento(nome).split())
                existente = explicitos.get(chave)
                if existente is None or existente[1].confianca < linha.confianca:
                    explicitos[chave] = (nome, linha)
    if len(explicitos) > 1:
        return Campo(estado="ambiguo", candidatos=[nome[:120] for nome, _ in explicitos.values()][:5],
                     motivo="mais de um estabelecimento identificado no comprovante")
    if explicitos:
        (nome, linha), = explicitos.values()
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
