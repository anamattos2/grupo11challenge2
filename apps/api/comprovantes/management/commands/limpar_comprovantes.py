"""Remove comprovantes vencidos e arquivos sem registro.

Uso: ``python manage.py limpar_comprovantes [--simular]``. Deve rodar
periodicamente (cron ou agendador da implantação), por exemplo a cada hora.
"""
from datetime import timedelta
from pathlib import Path
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from comprovantes.armazenamento import remover
from comprovantes.models import Comprovante

# Arquivo sem registro só é apagado depois deste tempo, para não pegar um envio em andamento.
TOLERANCIA_ORFAOS = timedelta(hours=1)


class Command(BaseCommand):
    help = "Apaga comprovantes com retenção vencida e arquivos órfãos da pasta privada."

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true", help="Só conta, sem apagar nada.")

    def handle(self, *args, simular=False, **options):
        vencidos = Comprovante.objects.expirados()
        total_vencidos = vencidos.count()
        if not simular:
            for comprovante in vencidos.iterator():
                comprovante.delete()  # o sinal remove o arquivo

        pasta = Path(settings.COMPROVANTES_DIR)
        conhecidos = {c.caminho.name for c in Comprovante.objects.all().only("id", "formato")}
        limite = time.time() - TOLERANCIA_ORFAOS.total_seconds()
        orfaos = [p for p in pasta.glob("*") if p.is_file() and p.name not in conhecidos
                  and p.stat().st_mtime < limite] if pasta.exists() else []
        if not simular:
            for caminho in orfaos:
                remover(caminho)

        acao = "Seriam apagados" if simular else "Apagados"
        self.stdout.write(f"{acao}: {total_vencidos} comprovante(s) vencido(s), {len(orfaos)} arquivo(s) órfão(s).")
