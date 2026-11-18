from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings

from tests.recurso_ficticio import AnotacaoFicticia

JSON = "application/json"


@override_settings(ROOT_URLCONF="tests.recurso_ficticio")
class IsolamentoEntreUsuariasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # A tabela é desfeita com a transação da classe de teste.
        with connection.schema_editor() as editor:
            editor.create_model(AnotacaoFicticia)

        Usuaria = get_user_model()
        cls.ana = Usuaria.objects.create_user("ana.ficticia")
        cls.bia = Usuaria.objects.create_user("bia.ficticia")

    def setUp(self):
        self.da_ana = AnotacaoFicticia.objects.create(usuaria=self.ana, titulo="Nota da Ana")
        self.da_bia = AnotacaoFicticia.objects.create(usuaria=self.bia, titulo="Nota da Bia")
        self.client.force_login(self.ana)

    def url(self, anotacao_id):
        return f"/api/anotacoes/{anotacao_id}"

    def test_listagem_retorna_somente_registros_proprios(self):
        resposta = self.client.get("/api/anotacoes")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual([item["id"] for item in resposta.json()], [self.da_ana.id])

    def test_consulta_o_proprio_registro_por_id(self):
        resposta = self.client.get(self.url(self.da_ana.id))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["titulo"], "Nota da Ana")

    def test_nao_consulta_registro_de_outra_usuaria_por_id(self):
        resposta = self.client.get(self.url(self.da_bia.id))

        self.assertEqual(resposta.status_code, 404)
        self.assertNotIn("Nota da Bia", resposta.content.decode())

    def test_id_alheio_e_id_inexistente_tem_a_mesma_resposta(self):
        alheio = self.client.get(self.url(self.da_bia.id))
        inexistente = self.client.get(self.url(self.da_bia.id + 1000))

        self.assertEqual(alheio.status_code, inexistente.status_code)
        self.assertEqual(alheio.content, inexistente.content)

    def test_nao_altera_registro_de_outra_usuaria_por_id(self):
        resposta = self.client.put(
            self.url(self.da_bia.id), {"titulo": "Invadido"}, content_type=JSON
        )

        self.assertEqual(resposta.status_code, 404)
        self.da_bia.refresh_from_db()
        self.assertEqual(self.da_bia.titulo, "Nota da Bia")

    def test_nao_exclui_registro_de_outra_usuaria_por_id(self):
        resposta = self.client.delete(self.url(self.da_bia.id))

        self.assertEqual(resposta.status_code, 404)
        self.assertTrue(AnotacaoFicticia.objects.filter(id=self.da_bia.id).exists())

    def test_dona_altera_e_exclui_o_proprio_registro(self):
        alterado = self.client.put(
            self.url(self.da_ana.id), {"titulo": "Nota revisada"}, content_type=JSON
        )
        excluido = self.client.delete(self.url(self.da_ana.id))

        self.assertEqual(alterado.status_code, 200)
        self.assertEqual(alterado.json()["titulo"], "Nota revisada")
        self.assertEqual(excluido.status_code, 204)
        self.assertFalse(AnotacaoFicticia.objects.filter(id=self.da_ana.id).exists())

    def test_criacao_ignora_dona_informada_pelo_cliente(self):
        resposta = self.client.post(
            "/api/anotacoes",
            {"titulo": "Nova", "usuaria_id": self.bia.id, "usuaria": self.bia.id},
            content_type=JSON,
        )

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["usuaria_id"], self.ana.id)

    def test_sessoes_simultaneas_veem_apenas_os_proprios_registros(self):
        cliente_bia = Client()
        cliente_bia.force_login(self.bia)

        ids_ana = [item["id"] for item in self.client.get("/api/anotacoes").json()]
        ids_bia = [item["id"] for item in cliente_bia.get("/api/anotacoes").json()]

        self.assertEqual(ids_ana, [self.da_ana.id])
        self.assertEqual(ids_bia, [self.da_bia.id])

    def test_sem_sessao_nenhuma_operacao_acessa_ou_modifica_dados(self):
        anonimo = Client()
        url = self.url(self.da_ana.id)
        corpo = {"data": {"titulo": "Anônimo"}, "content_type": JSON}

        respostas = [
            anonimo.get("/api/anotacoes"),
            anonimo.post("/api/anotacoes", **corpo),
            anonimo.get(url),
            anonimo.put(url, **corpo),
            anonimo.delete(url),
        ]

        self.assertEqual([r.status_code for r in respostas], [401] * 5)
        self.da_ana.refresh_from_db()
        self.assertEqual(self.da_ana.titulo, "Nota da Ana")
        self.assertEqual(AnotacaoFicticia.objects.count(), 2)
