import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings import env


class EnvTests(SimpleTestCase):
    def test_retorna_valor_definido_no_ambiente(self):
        with mock.patch.dict(os.environ, {"VARIAVEL_FICTICIA": "valor"}):
            self.assertEqual(env("VARIAVEL_FICTICIA"), "valor")

    def test_recusa_variavel_ausente_ou_vazia(self):
        with mock.patch.dict(os.environ, {"VARIAVEL_FICTICIA": ""}):
            with self.assertRaisesMessage(ImproperlyConfigured, "VARIAVEL_FICTICIA"):
                env("VARIAVEL_FICTICIA")
