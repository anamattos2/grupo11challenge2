"""Apagar o registro (pela rota, pela limpeza ou ao excluir a usuária) apaga o arquivo."""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .armazenamento import remover
from .models import Comprovante


@receiver(post_delete, sender=Comprovante, dispatch_uid="comprovante_remove_arquivo")
def remover_arquivo(sender, instance, **kwargs):
    remover(instance.caminho)
