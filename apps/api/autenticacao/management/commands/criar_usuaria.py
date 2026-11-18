"""Cria uma usuária comum, sem expor a senha no histórico do terminal."""
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Cria uma usuária comum, solicitando a senha de forma interativa."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        usuaria = get_user_model()(username=options["username"])
        senha = getpass("Senha: ")
        if senha != getpass("Confirme a senha: "):
            raise CommandError("As senhas não coincidem.")

        try:
            usuaria.full_clean(exclude=["password"])
            validate_password(senha, usuaria)
        except ValidationError as erro:
            raise CommandError(" ".join(erro.messages)) from erro

        usuaria.set_password(senha)
        usuaria.save()
        self.stdout.write(self.style.SUCCESS(f"Usuária {usuaria.username} criada."))
