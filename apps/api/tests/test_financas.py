from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase

from financas.models import ContaManual, PerfilFinanceiro

JSON = "application/json"
CONTA = {"nome": "Conta principal", "tipo": "corrente", "saldo_declarado": "1500.50"}


class BaseFinancas(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuaria = get_user_model()
        cls.ana = Usuaria.objects.create_user("ana.ficticia")
        cls.bia = Usuaria.objects.create_user("bia.ficticia")

    def setUp(self):
        self.client.force_login(self.ana)

    def enviar(self, metodo, url, dados, cliente=None):
        return getattr(cliente or self.client, metodo)(url, dados, content_type=JSON)

    def criar_conta(self, usuaria=None, **campos):
        dados = {
            "nome": "Conta principal",
            "tipo": ContaManual.Tipo.CORRENTE,
            "saldo_declarado": Decimal("100.00"),
            **campos,
        }
        return ContaManual.objects.create(usuaria=usuaria or self.ana, **dados)


class PerfilTests(BaseFinancas):
    def test_consulta_antes_de_criar_responde_404(self):
        self.assertEqual(self.client.get("/api/perfil").status_code, 404)

    def test_cria_e_consulta_o_proprio_perfil(self):
        criado = self.enviar(
            "put",
            "/api/perfil",
            {"nome_exibicao": "  Clara Exemplo ", "previsibilidade_renda": "fixa"},
        )
        consultado = self.client.get("/api/perfil")

        self.assertEqual(criado.status_code, 201)
        self.assertEqual(consultado.status_code, 200)
        self.assertEqual(consultado.json()["nome_exibicao"], "Clara Exemplo")
        self.assertEqual(consultado.json()["previsibilidade_renda"], "fixa")

    def test_previsibilidade_nao_informada_e_o_padrao(self):
        resposta = self.enviar("put", "/api/perfil", {"nome_exibicao": "Clara Exemplo"})

        self.assertEqual(resposta.json()["previsibilidade_renda"], "nao_informada")

    def test_edicao_atualiza_o_perfil_existente_sem_duplicar(self):
        self.enviar("put", "/api/perfil", {"nome_exibicao": "Clara Exemplo"})

        editado = self.enviar(
            "put",
            "/api/perfil",
            {"nome_exibicao": "Clara Revisada", "previsibilidade_renda": "variavel"},
        )

        self.assertEqual(editado.status_code, 200)
        self.assertEqual(editado.json()["nome_exibicao"], "Clara Revisada")
        self.assertEqual(PerfilFinanceiro.objects.count(), 1)

    def test_recusa_dados_invalidos(self):
        invalidos = [
            {},
            {"nome_exibicao": "   "},
            {"nome_exibicao": "x" * 81},
            {"nome_exibicao": "Clara\x00Exemplo"},
            {"nome_exibicao": "Clara", "previsibilidade_renda": "desconhecida"},
            {"nome_exibicao": "Clara", "usuaria_id": self.bia.id},
        ]

        for dados in invalidos:
            with self.subTest(dados=dados):
                resposta = self.enviar("put", "/api/perfil", dados)
                self.assertEqual(resposta.status_code, 422)
        self.assertFalse(PerfilFinanceiro.objects.exists())

    def test_cada_usuaria_mantem_o_proprio_perfil(self):
        cliente_bia = Client()
        cliente_bia.force_login(self.bia)
        self.enviar("put", "/api/perfil", {"nome_exibicao": "Perfil da Ana"})

        self.assertEqual(cliente_bia.get("/api/perfil").status_code, 404)

        self.enviar("put", "/api/perfil", {"nome_exibicao": "Perfil da Bia"}, cliente_bia)
        self.assertEqual(self.client.get("/api/perfil").json()["nome_exibicao"], "Perfil da Ana")
        self.assertEqual(cliente_bia.get("/api/perfil").json()["nome_exibicao"], "Perfil da Bia")


class ContaTests(BaseFinancas):
    def test_cria_conta_para_a_usuaria_autenticada(self):
        resposta = self.enviar("post", "/api/contas", CONTA)

        self.assertEqual(resposta.status_code, 201)
        corpo = resposta.json()
        self.assertEqual(corpo["nome"], "Conta principal")
        self.assertEqual(corpo["tipo"], "corrente")
        self.assertEqual(corpo["saldo_declarado"], "1500.50")
        self.assertEqual(corpo["moeda"], "BRL")
        self.assertEqual(ContaManual.objects.get(id=corpo["id"]).usuaria, self.ana)

    def test_edita_nome_tipo_e_saldo_da_propria_conta(self):
        conta = self.criar_conta()

        resposta = self.enviar(
            "put",
            f"/api/contas/{conta.id}",
            {"nome": "Reserva", "tipo": "reserva", "saldo_declarado": "600"},
        )

        self.assertEqual(resposta.status_code, 200)
        conta.refresh_from_db()
        self.assertEqual(conta.nome, "Reserva")
        self.assertEqual(conta.tipo, ContaManual.Tipo.RESERVA)
        self.assertEqual(conta.saldo_declarado, Decimal("600.00"))
        self.assertEqual(resposta.json()["saldo_declarado"], "600.00")

    def test_saldo_preserva_valor_decimal_exato(self):
        casos = {
            "0.10": "0.10",
            "1234.5": "1234.50",
            "-250.75": "-250.75",
            "-0.00": "0.00",
            "999999999999.99": "999999999999.99",
        }

        for indice, (entrada, esperado) in enumerate(casos.items()):
            with self.subTest(entrada=entrada):
                dados = {**CONTA, "nome": f"Conta {indice}", "saldo_declarado": entrada}
                resposta = self.enviar("post", "/api/contas", dados)
                self.assertEqual(resposta.status_code, 201)
                self.assertEqual(resposta.json()["saldo_declarado"], esperado)
                conta = ContaManual.objects.get(id=resposta.json()["id"])
                self.assertEqual(conta.saldo_declarado, Decimal(esperado))

    def test_recusa_saldo_invalido(self):
        invalidos = [
            10.5,
            10,
            None,
            True,
            "",
            "abc",
            "10,50",
            "1.234",
            "1e3",
            "NaN",
            "Infinity",
            " 10.00",
            "10.00\n",
            "١٠",
            "1000000000000.00",
        ]

        for saldo in invalidos:
            with self.subTest(saldo=saldo):
                resposta = self.enviar(
                    "post", "/api/contas", {**CONTA, "saldo_declarado": saldo}
                )
                self.assertEqual(resposta.status_code, 422)
        self.assertFalse(ContaManual.objects.exists())

    def test_recusa_nome_tipo_e_campos_invalidos(self):
        invalidos = [
            {**CONTA, "nome": "   "},
            {**CONTA, "nome": "x" * 81},
            {**CONTA, "nome": "Conta\x00principal"},
            {**CONTA, "tipo": "investimento"},
            {**CONTA, "moeda": "USD"},
            {**CONTA, "usuaria_id": self.bia.id},
            {"nome": "Conta principal", "tipo": "corrente"},
        ]

        for dados in invalidos:
            with self.subTest(dados=dados):
                self.assertEqual(self.enviar("post", "/api/contas", dados).status_code, 422)
        self.assertFalse(ContaManual.objects.exists())

    def test_edicao_invalida_nao_altera_a_conta(self):
        conta = self.criar_conta()

        resposta = self.enviar(
            "put", f"/api/contas/{conta.id}", {**CONTA, "saldo_declarado": "abc"}
        )

        self.assertEqual(resposta.status_code, 422)
        conta.refresh_from_db()
        self.assertEqual(conta.saldo_declarado, Decimal("100.00"))

    def test_recusa_nome_repetido_sem_diferenciar_caixa(self):
        self.criar_conta(nome="Reserva")

        resposta = self.enviar("post", "/api/contas", {**CONTA, "nome": "RESERVA"})

        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(resposta.json(), {"detail": "Já existe uma conta com este nome."})
        self.assertEqual(ContaManual.objects.count(), 1)

    def test_edicao_recusa_nome_de_outra_conta_propria(self):
        self.criar_conta(nome="Reserva")
        conta = self.criar_conta(nome="Carteira")

        resposta = self.enviar("put", f"/api/contas/{conta.id}", {**CONTA, "nome": "reserva"})

        self.assertEqual(resposta.status_code, 409)
        conta.refresh_from_db()
        self.assertEqual(conta.nome, "Carteira")

    def test_edicao_pode_manter_o_proprio_nome(self):
        conta = self.criar_conta()

        resposta = self.enviar("put", f"/api/contas/{conta.id}", CONTA)

        self.assertEqual(resposta.status_code, 200)

    def test_usuarias_diferentes_podem_usar_o_mesmo_nome(self):
        self.criar_conta(usuaria=self.bia)

        self.assertEqual(self.enviar("post", "/api/contas", CONTA).status_code, 201)


class IsolamentoDeContasTests(BaseFinancas):
    def setUp(self):
        super().setUp()
        self.da_ana = self.criar_conta(nome="Conta da Ana")
        self.da_bia = self.criar_conta(usuaria=self.bia, nome="Conta da Bia")

    def test_listagem_retorna_somente_contas_proprias(self):
        resposta = self.client.get("/api/contas")

        self.assertEqual([conta["id"] for conta in resposta.json()], [self.da_ana.id])

    def test_nao_consulta_conta_de_outra_usuaria_por_id(self):
        alheia = self.client.get(f"/api/contas/{self.da_bia.id}")
        inexistente = self.client.get(f"/api/contas/{self.da_bia.id + 1000}")

        self.assertEqual(alheia.status_code, 404)
        self.assertEqual(alheia.content, inexistente.content)

    def test_nao_edita_conta_de_outra_usuaria_por_id(self):
        resposta = self.enviar("put", f"/api/contas/{self.da_bia.id}", CONTA)

        self.assertEqual(resposta.status_code, 404)
        self.da_bia.refresh_from_db()
        self.assertEqual(self.da_bia.nome, "Conta da Bia")
        self.assertEqual(self.da_bia.saldo_declarado, Decimal("100.00"))

    def test_id_fora_do_intervalo_responde_404(self):
        resposta = self.client.get(f"/api/contas/{10**30}")

        self.assertEqual(resposta.status_code, 404)

    def test_sem_sessao_nenhuma_operacao_acessa_ou_modifica_contas(self):
        anonimo = Client()
        url = f"/api/contas/{self.da_ana.id}"

        respostas = [
            anonimo.get("/api/contas"),
            self.enviar("post", "/api/contas", CONTA, anonimo),
            anonimo.get(url),
            self.enviar("put", url, CONTA, anonimo),
            anonimo.get("/api/perfil"),
            self.enviar("put", "/api/perfil", {"nome_exibicao": "Anônima"}, anonimo),
        ]

        self.assertEqual([r.status_code for r in respostas], [401] * 6)
        self.da_ana.refresh_from_db()
        self.assertEqual(self.da_ana.nome, "Conta da Ana")
        self.assertEqual(ContaManual.objects.count(), 2)
        self.assertFalse(PerfilFinanceiro.objects.exists())

    def test_escrita_sem_token_csrf_e_recusada(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.ana)

        conta = self.enviar("post", "/api/contas", CONTA, cliente)
        perfil = self.enviar("put", "/api/perfil", {"nome_exibicao": "Clara"}, cliente)

        self.assertEqual(conta.status_code, 403)
        self.assertEqual(perfil.status_code, 403)
        self.assertEqual(ContaManual.objects.count(), 2)


class ContratoTests(TestCase):
    def test_contrato_versionado_esta_em_dia(self):
        call_command("exportar_contrato", "--check")

    def test_saldo_e_publicado_como_texto_decimal(self):
        contrato = self.client.get("/api/openapi.json").json()
        esquemas = contrato["components"]["schemas"]

        for nome in ("ContaIn", "ContaOut"):
            saldo = esquemas[nome]["properties"]["saldo_declarado"]
            self.assertEqual(saldo["type"], "string")
