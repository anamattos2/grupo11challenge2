"""Validação e limpeza de imagens de comprovante (S5-01 / #95).

A decisão sobre o formato vem do conteúdo do arquivo, nunca do nome nem do
``Content-Type`` enviado pelo navegador. Toda imagem aceita é decodificada e
gravada de novo pelo Pillow: isso descarta metadados (EXIF com localização,
modelo do celular, data) e qualquer coisa escondida depois dos dados da imagem.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import warnings

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

# Assinaturas (magic bytes) dos formatos aceitos.
_ASSINATURAS = {
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
}
FORMATOS = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
EXTENSOES = {"jpeg": "jpg", "png": "png", "webp": "webp"}


class ImagemRecusada(ValueError):
    """Arquivo recusado. ``codigo`` e ``status`` vão para a resposta HTTP."""

    def __init__(self, codigo: str, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.status = codigo, mensagem, status


@dataclass(frozen=True)
class ImagemLimpa:
    formato: str
    conteudo: bytes
    largura: int
    altura: int

    @property
    def mime(self) -> str:
        return FORMATOS[self.formato]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.conteudo).hexdigest()


def formato_pela_assinatura(inicio: bytes) -> str | None:
    for formato, assinaturas in _ASSINATURAS.items():
        if any(inicio.startswith(a) for a in assinaturas):
            return formato
    if inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP":
        return "webp"
    return None


def validar_e_limpar(conteudo: bytes) -> ImagemLimpa:
    """Valida tamanho, formato real e integridade; devolve a imagem regravada."""
    limite = settings.COMPROVANTES_TAMANHO_MAXIMO_BYTES
    if not conteudo:
        raise ImagemRecusada("arquivo_vazio", "O arquivo está vazio.")
    if len(conteudo) > limite:
        raise ImagemRecusada("arquivo_grande_demais",
                             f"O arquivo passa do limite de {limite // (1024 * 1024)} MB.", 413)

    formato = formato_pela_assinatura(conteudo[:16])
    if formato is None:
        raise ImagemRecusada("formato_nao_suportado", "Envie uma imagem JPEG, PNG ou WebP.", 415)

    maximo_pixels = settings.COMPROVANTES_MAXIMO_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(conteudo)) as imagem:
                if (imagem.format or "").lower() != formato:
                    raise ImagemRecusada("formato_nao_suportado", "O conteúdo não corresponde a uma imagem aceita.", 415)
                if imagem.width * imagem.height > maximo_pixels:
                    raise ImagemRecusada("imagem_grande_demais", "A imagem tem resolução maior que a permitida.")
                imagem.load()  # decodifica de verdade: arquivo truncado ou corrompido falha aqui
                imagem = ImageOps.exif_transpose(imagem)  # mantém a orientação antes de descartar o EXIF
                if formato == "jpeg" and imagem.mode not in ("RGB", "L"):
                    imagem = imagem.convert("RGB")
                saida = BytesIO()
                opcoes = {"quality": 90} if formato in ("jpeg", "webp") else {"optimize": True}
                imagem.save(saida, format=formato.upper(), **opcoes)
                largura, altura = imagem.size
    except ImagemRecusada:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise ImagemRecusada("imagem_invalida", "Não foi possível ler a imagem enviada.") from None

    return ImagemLimpa(formato=formato, conteudo=saida.getvalue(), largura=largura, altura=altura)
