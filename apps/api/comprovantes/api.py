"""Rotas de upload de comprovantes (S5-01 / #95).

Todas exigem sessão (``django_auth``: sessão do Django e, em escrita, token
CSRF). A dona do comprovante vem sempre de ``request.user``; nenhum campo do
formulário, da URL ou de agente de IA escolhe a usuária. Comprovante de outra
pessoa, inexistente ou expirado responde do mesmo jeito: 404.

O upload só guarda a imagem. Não cria despesa nem transação: isso acontece
depois, na confirmação explícita da prévia (RF17).
"""
from datetime import datetime, timedelta
import logging
from uuid import UUID

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from ninja import File, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.security import django_auth

from .armazenamento import gravar
from .extracao import ExtracaoOut, OCRIndisponivel, extrair
from .imagens import EXTENSOES, ImagemRecusada, validar_e_limpar
from .models import Comprovante

logger = logging.getLogger("comprovantes")
router = Router(tags=["comprovantes"], auth=django_auth)


class ComprovanteOut(Schema):
    id: UUID
    formato: str
    tipo_mime: str
    tamanho_bytes: int
    largura: int
    altura: int
    criado_em: datetime
    expira_em: datetime

    @staticmethod
    def resolve_tipo_mime(obj):
        return obj.mime


class ErroOut(Schema):
    codigo: str
    detail: str


def _do_proprio(request, comprovante_id: UUID) -> Comprovante:
    """Busca só entre os comprovantes vigentes da usuária da sessão."""
    comprovante = (Comprovante.objects.da_usuaria(request.user).vigentes()
                   .filter(id=comprovante_id).first())
    if comprovante is None:
        raise HttpError(404, "Comprovante não encontrado.")
    return comprovante


def _recusar(request, erro: ImagemRecusada, tamanho: int):
    logger.info("comprovante recusado usuaria=%s motivo=%s tamanho=%d",
                request.user.pk, erro.codigo, tamanho)
    return erro.status, {"codigo": erro.codigo, "detail": erro.mensagem}


@router.post("", response={201: ComprovanteOut, 400: ErroOut, 413: ErroOut, 415: ErroOut, 429: ErroOut},
             summary="Enviar imagem de comprovante")
def enviar(request, arquivo: UploadedFile = File(...)):
    """Recebe JPEG, PNG ou WebP, valida e guarda uma cópia sem metadados."""
    limite_hora = settings.COMPROVANTES_ENVIOS_POR_HORA
    recentes = Comprovante.objects.da_usuaria(request.user).filter(
        criado_em__gte=timezone.now() - timedelta(hours=1)).count()
    if recentes >= limite_hora:
        logger.info("comprovante recusado usuaria=%s motivo=limite_de_envios", request.user.pk)
        return 429, {"codigo": "limite_de_envios", "detail": "Muitos envios na última hora. Tente mais tarde."}

    if arquivo.size > settings.COMPROVANTES_TAMANHO_MAXIMO_BYTES:  # recusa antes de ler o conteúdo
        limite = settings.COMPROVANTES_TAMANHO_MAXIMO_BYTES
        return _recusar(request, ImagemRecusada(
            "arquivo_grande_demais", f"O arquivo passa do limite de {limite // (1024 * 1024)} MB.", 413), arquivo.size)
    try:
        imagem = validar_e_limpar(arquivo.read())
    except ImagemRecusada as erro:
        return _recusar(request, erro, arquivo.size)

    comprovante = Comprovante(usuaria=request.user, formato=imagem.formato, tamanho_bytes=len(imagem.conteudo),
                              largura=imagem.largura, altura=imagem.altura, sha256=imagem.sha256)
    gravar(comprovante.caminho, imagem.conteudo)
    try:
        comprovante.save()
    except Exception:
        comprovante.caminho.unlink(missing_ok=True)
        raise
    logger.info("comprovante recebido id=%s usuaria=%s formato=%s tamanho=%d",
                comprovante.id, request.user.pk, comprovante.formato, comprovante.tamanho_bytes)
    return 201, comprovante


@router.get("", response=list[ComprovanteOut], summary="Listar meus comprovantes")
def listar(request):
    return Comprovante.objects.da_usuaria(request.user).vigentes()


@router.get("/{comprovante_id}", response=ComprovanteOut, summary="Ver dados de um comprovante")
def detalhar(request, comprovante_id: UUID):
    return _do_proprio(request, comprovante_id)


@router.get("/{comprovante_id}/arquivo", summary="Baixar a imagem de um comprovante",
            response={200: None, 404: ErroOut})
def baixar(request, comprovante_id: UUID):
    comprovante = _do_proprio(request, comprovante_id)
    try:
        conteudo = comprovante.caminho.read_bytes()
    except FileNotFoundError:
        raise HttpError(404, "Comprovante não encontrado.") from None
    resposta = HttpResponse(conteudo, content_type=comprovante.mime)
    resposta["Content-Disposition"] = f'inline; filename="comprovante.{EXTENSOES[comprovante.formato]}"'
    resposta["Cache-Control"] = "private, no-store"
    resposta["X-Content-Type-Options"] = "nosniff"
    return resposta


@router.delete("/{comprovante_id}", response={204: None}, summary="Excluir um comprovante")
def excluir(request, comprovante_id: UUID):
    comprovante = _do_proprio(request, comprovante_id)
    identificador = comprovante.id
    comprovante.delete()  # o sinal post_delete remove o arquivo
    logger.info("comprovante excluido id=%s usuaria=%s", identificador, request.user.pk)
    return 204, None


@router.post("/{comprovante_id}/extracao", response={200: ExtracaoOut, 404: ErroOut, 503: ErroOut},
             summary="Extrair valor, data e estabelecimento")
def extrair_campos(request, comprovante_id: UUID):
    """Lê a imagem e devolve os campos com estado presente, ausente ou ambíguo.

    Não cria despesa: o resultado alimenta a prévia editável (RF17).
    """
    comprovante = _do_proprio(request, comprovante_id)
    try:
        resultado = extrair(comprovante)
    except OCRIndisponivel as erro:
        logger.warning("comprovante extracao indisponivel id=%s usuaria=%s motivo=%s",
                       comprovante.id, request.user.pk, erro.codigo)
        return 503, {"codigo": erro.codigo,
                     "detail": "A leitura automática está indisponível agora. Preencha os campos manualmente "
                               "ou tente de novo mais tarde."}
    except FileNotFoundError:
        raise HttpError(404, "Comprovante não encontrado.") from None
    campos = resultado.campos
    logger.info("comprovante extracao id=%s usuaria=%s status=%s valor=%s data=%s estabelecimento=%s",
                comprovante.id, request.user.pk, resultado.status, campos.valor_total.estado,
                campos.data.estado, campos.estabelecimento.estado)
    return 200, resultado
