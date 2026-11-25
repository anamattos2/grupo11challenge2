"""Comprovante enviado por imagem: metadados no PostgreSQL, arquivo em pasta privada.

O nome original do arquivo não é guardado nem registrado em log: ele pode conter
nome de pessoa, de loja ou de banco. O arquivo fica em
``COMPROVANTES_DIR/<id>.<extensão>``, fora de qualquer pasta servida
diretamente, e só sai pela rota autenticada da própria dona.
"""
from datetime import timedelta
from pathlib import Path
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .imagens import EXTENSOES, FORMATOS


class ComprovanteQuerySet(models.QuerySet):
    def da_usuaria(self, usuaria):
        return self.filter(usuaria=usuaria)

    def vigentes(self, agora=None):
        return self.filter(expira_em__gt=agora or timezone.now())

    def expirados(self, agora=None):
        return self.filter(expira_em__lte=agora or timezone.now())


def prazo_de_retencao():
    return timezone.now() + timedelta(hours=settings.COMPROVANTES_RETENCAO_HORAS)


class Comprovante(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuaria = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="+", editable=False)
    formato = models.CharField(max_length=8, choices=[(f, f) for f in FORMATOS])
    tamanho_bytes = models.PositiveIntegerField()
    largura = models.PositiveIntegerField()
    altura = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64, help_text="Hash da imagem já limpa; base para detectar duplicação provável.")
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField(default=prazo_de_retencao, db_index=True)

    objects = ComprovanteQuerySet.as_manager()

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["usuaria", "-criado_em"], name="comprovante_usuaria_idx")]

    @property
    def mime(self) -> str:
        return FORMATOS[self.formato]

    @property
    def caminho(self) -> Path:
        return Path(settings.COMPROVANTES_DIR) / f"{self.id}.{EXTENSOES[self.formato]}"
