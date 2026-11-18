from unittest import mock

from django.db import OperationalError
from django.test import TestCase


class HealthTests(TestCase):
    def test_confirma_conexao_com_postgresql(self):
        resposta = self.client.get("/api/health")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok", "database": "ok"})

    def test_informa_indisponibilidade_do_banco(self):
        with mock.patch(
            "config.api.connection.cursor",
            side_effect=OperationalError("banco fictício indisponível"),
        ):
            resposta = self.client.get("/api/health")

        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json(), {"status": "indisponivel", "database": "erro"})

    def test_publica_contrato_openapi_e_documentacao(self):
        contrato = self.client.get("/api/openapi.json")
        documentacao = self.client.get("/api/docs")

        self.assertEqual(contrato.status_code, 200)
        self.assertIn("/api/health", contrato.json()["paths"])
        self.assertEqual(documentacao.status_code, 200)
