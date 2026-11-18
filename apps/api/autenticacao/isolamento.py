"""Base para registros que pertencem a uma única usuária.

Modelos financeiros devem herdar de ``RegistroDaUsuaria``. Nas rotas, a usuária
vem sempre de ``request.auth``, nunca do corpo, da URL ou de um agente de IA.
"""
from django.conf import settings
from django.db import models
from django.shortcuts import get_object_or_404


class RegistroDaUsuariaQuerySet(models.QuerySet):
    def da_usuaria(self, usuaria):
        return self.filter(usuaria=usuaria)


class RegistroDaUsuaria(models.Model):
    usuaria = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        editable=False,
    )

    objects = RegistroDaUsuariaQuerySet.as_manager()

    class Meta:
        abstract = True


def obter_da_usuaria_ou_404(modelo, usuaria, **filtros):
    """Busca um registro próprio; o de outra usuária responde como inexistente."""
    return get_object_or_404(modelo.objects.da_usuaria(usuaria), **filtros)
