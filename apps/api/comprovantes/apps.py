from django.apps import AppConfig


class ComprovantesConfig(AppConfig):
    name = "comprovantes"
    verbose_name = "Comprovantes por imagem"

    def ready(self):
        from . import sinais  # noqa: F401  (remove o arquivo quando o registro é apagado)
