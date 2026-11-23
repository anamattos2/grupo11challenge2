"""Leitura de texto (OCR) das imagens de comprovante.

O motor é trocável: o padrão é o Tesseract (``pytesseract``), que roda local,
sem enviar a imagem para fora. Qualquer problema do motor (programa ausente,
idioma não instalado, tempo esgotado, falha interna) vira ``OCRIndisponivel``,
que a rota transforma em 503. Nunca vira "não encontrei nada".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import statistics
from typing import Protocol

from django.conf import settings
from PIL import Image, ImageOps


class OCRIndisponivel(RuntimeError):
    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True)
class Linha:
    texto: str
    confianca: float  # média 0–100 das palavras da linha; -1 quando o motor não informa


@dataclass(frozen=True)
class Leitura:
    linhas: list[Linha] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(l.texto for l in self.linhas)

    @property
    def confianca_media(self) -> float:
        valores = [l.confianca for l in self.linhas if l.confianca >= 0]
        return statistics.fmean(valores) if valores else -1.0


class MotorOCR(Protocol):
    nome: str

    def ler(self, imagem: bytes) -> Leitura: ...


def _angulo_de_inclinacao(figura: Image.Image, limite: float = 6.0, passo: float = 0.5) -> float:
    """Ângulo que deixa as linhas de texto mais "retas" (perfil de projeção).

    Com o texto alinhado, as médias por linha de pixels alternam entre linhas
    escuras (texto) e claras (entrelinha), e a variância é máxima. Só usa
    Pillow: reduzir a imagem para 1 coluna dá a média de cada linha.
    """
    pequena = ImageOps.invert(figura).resize((max(1, figura.width * 300 // max(figura.height, 1)) or 1, 300)
                                              if figura.height > 300 else figura.size)
    melhor, angulo = -1.0, 0.0
    passos = int(limite / passo)
    for i in range(-passos, passos + 1):
        candidato = i * passo
        girada = pequena.rotate(candidato, expand=True, fillcolor=0)
        perfil = list(girada.resize((1, girada.height), Image.Resampling.BOX).getdata())
        media = sum(perfil) / len(perfil)
        variancia = sum((v - media) ** 2 for v in perfil) / len(perfil)
        if variancia > melhor + 1e-9:
            melhor, angulo = variancia, candidato
    return angulo


def preparar(imagem: bytes) -> Image.Image:
    """Tons de cinza, contraste automático, endireitamento e ampliação de imagens pequenas."""
    with Image.open(BytesIO(imagem)) as original:
        figura = ImageOps.autocontrast(ImageOps.grayscale(original))
    angulo = _angulo_de_inclinacao(figura)
    if angulo:
        figura = figura.rotate(angulo, expand=True, fillcolor=255, resample=Image.Resampling.BICUBIC)
    if figura.width < 1000:
        fator = 1000 / figura.width
        figura = figura.resize((1000, max(1, round(figura.height * fator))), Image.Resampling.LANCZOS)
    return figura


class MotorTesseract:
    nome = "tesseract"

    def __init__(self, idioma: str | None = None, tempo_limite_s: float | None = None):
        self.idioma = idioma or settings.COMPROVANTES_OCR_IDIOMA
        self.tempo_limite_s = tempo_limite_s or settings.COMPROVANTES_OCR_TEMPO_LIMITE_S

    def ler(self, imagem: bytes) -> Leitura:
        try:
            import pytesseract
        except ImportError:
            raise OCRIndisponivel("ocr_nao_instalado") from None
        try:
            dados = pytesseract.image_to_data(preparar(imagem), lang=self.idioma, config="--psm 6",
                                              output_type=pytesseract.Output.DICT, timeout=self.tempo_limite_s)
        except pytesseract.TesseractNotFoundError:
            raise OCRIndisponivel("ocr_nao_instalado") from None
        except RuntimeError as erro:  # o pytesseract sinaliza o tempo esgotado com RuntimeError
            codigo = "ocr_tempo_esgotado" if "timeout" in str(erro).lower() else "ocr_falhou"
            raise OCRIndisponivel(codigo) from None
        except (pytesseract.TesseractError, OSError):
            raise OCRIndisponivel("ocr_falhou") from None

        linhas: dict[tuple, list[tuple[str, float]]] = {}
        for i, palavra in enumerate(dados["text"]):
            palavra = (palavra or "").strip()
            if not palavra:
                continue
            chave = (dados["block_num"][i], dados["par_num"][i], dados["line_num"][i])
            linhas.setdefault(chave, []).append((palavra, float(dados["conf"][i])))
        return Leitura([Linha(" ".join(p for p, _ in palavras), statistics.fmean(c for _, c in palavras))
                        for _, palavras in sorted(linhas.items())])


class MotorDesligado:
    nome = "desligado"

    def ler(self, imagem: bytes) -> Leitura:
        raise OCRIndisponivel("ocr_desligado")


def motor_configurado() -> MotorOCR:
    escolhido = settings.COMPROVANTES_OCR_MOTOR
    if escolhido == "tesseract":
        return MotorTesseract()
    return MotorDesligado()
