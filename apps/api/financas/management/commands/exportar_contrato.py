"""Exporta o contrato OpenAPI versionado em contracts/openapi.json."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ninja.responses import NinjaJSONEncoder

from config.api import api

CAMINHO_CONTRATO = settings.BASE_DIR.parent.parent / "contracts" / "openapi.json"
DESCRICAO_422 = "Unprocessable Content"


def normalizar_contrato(contrato: dict) -> dict:
    """Fixa o texto do status 422, que muda conforme a versão do Python."""
    for operacoes in contrato["paths"].values():
        for operacao in operacoes.values():
            if 422 in operacao["responses"]:
                operacao["responses"][422]["description"] = DESCRICAO_422
    return contrato


class Command(BaseCommand):
    help = "Atualiza o contrato OpenAPI ou, com --check, confere se ele está em dia."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        contrato = json.dumps(
            normalizar_contrato(api.get_openapi_schema()),
            cls=NinjaJSONEncoder,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        contrato += "\n"

        if not options["check"]:
            CAMINHO_CONTRATO.write_text(contrato, encoding="utf-8")
            return

        if not CAMINHO_CONTRATO.exists() or (
            CAMINHO_CONTRATO.read_text(encoding="utf-8") != contrato
        ):
            raise CommandError(
                "contracts/openapi.json está desatualizado. "
                "Execute manage.py exportar_contrato."
            )
