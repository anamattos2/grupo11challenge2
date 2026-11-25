"""Gravação e remoção dos arquivos de comprovante na pasta privada."""
import logging
import os
from pathlib import Path
import tempfile

from django.conf import settings

logger = logging.getLogger("comprovantes")


def pasta() -> Path:
    destino = Path(settings.COMPROVANTES_DIR)
    destino.mkdir(mode=0o700, parents=True, exist_ok=True)
    return destino


def gravar(caminho: Path, conteudo: bytes) -> None:
    """Grava de forma atômica e com permissão só para o dono do processo (0600)."""
    pasta()
    descritor, temporario = tempfile.mkstemp(dir=caminho.parent, prefix=".envio-")
    try:
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(conteudo)
        os.chmod(temporario, 0o600)
        os.replace(temporario, caminho)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise


def remover(caminho: Path) -> None:
    try:
        caminho.unlink(missing_ok=True)
    except OSError:
        # Não interrompe a exclusão do registro; o comando de limpeza tenta de novo.
        logger.warning("comprovante: falha ao remover arquivo %s", caminho.name)
