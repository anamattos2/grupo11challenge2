from datetime import date, timedelta
from decimal import Decimal
import json
import threading
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from financas.models import Categoria, ContaManual, TipoLancamento, Transacao

JSON = "application/json"
RECEITA = TipoLancamento.RECEITA
DESPESA = TipoLancamento.DESPESA


class BaseTransacoes(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuaria = get_user_model()
        cls.ana = Usuaria.objects.create_user("ana.ficticia")
        cls.bia = Usuaria.objects.create_user("bia.ficticia")
        cls.mercado = Categoria.objects.create(
            usuaria=cls.ana, nome="Mercado", tipo=DESPESA, essencial=True
        )
        cls.lazer = Categoria.objects.create(usuaria=cls.ana, nome="Lazer", tipo=DESPESA)
        cls.salario = Categoria.objects.create(usuaria=cls.ana, nome="Salário", tipo=RECEITA)
        cls.da_bia = Categoria.objects.create(usuaria=cls.bia, nome="Da Bia", tipo=DESPESA)

    def setUp(self):
        self.client.force_login(self.ana)

    def enviar(self, metodo, url, dados, cliente=None):
        return getattr(cliente or self.client, metodo)(url, dados, content_type=JSON)

    def corpo(self, **campos):
        return {
            "tipo": "despesa",
            "valor": "89.90",
            "data": "2026-03-10",
            "categoria_id": self.mercado.id,
            **campos,
        }

    def transacao(self, usuaria=None, categoria=None, **campos):
        categoria = categoria or self.mercado
        dados = {
            "tipo": categoria.tipo,
            "valor": Decimal("10.00"),
            "data": date(2026, 3, 10),
            **campos,
        }
        return Transacao.objects.create(usuaria=usuaria or self.ana, categoria=categoria, **dados)


class CategoriaTests(BaseTransacoes):
    def test_cria_e_consulta_categoria(self):
        criada = self.enviar(
            "post",
            "/api/categorias",
            {"nome": " Moradia ", "tipo": "despesa", "essencial": True},
        )

        self.assertEqual(criada.status_code, 201)
        consultada = self.client.get(f"/api/categorias/{criada.json()['id']}").json()
        self.assertEqual(consultada["nome"], "Moradia")
        self.assertTrue(consultada["essencial"])

    def test_edita_categoria(self):
        resposta = self.enviar(
            "put",
            f"/api/categorias/{self.lazer.id}",
            {"nome": "Passeios", "tipo": "despesa", "essencial": True},
        )

        self.assertEqual(resposta.status_code, 200)
        self.lazer.refresh_from_db()
        self.assertEqual(self.lazer.nome, "Passeios")
        self.assertTrue(self.lazer.essencial)

    def test_recusa_nome_repetido_no_mesmo_tipo_sem_diferenciar_caixa(self):
        resposta = self.enviar("post", "/api/categorias", {"nome": "MERCADO", "tipo": "despesa"})

        self.assertEqual(resposta.status_code, 409)

    def test_edicao_recusa_nome_de_outra_categoria(self):
        resposta = self.enviar(
            "put", f"/api/categorias/{self.lazer.id}", {"nome": "mercado", "tipo": "despesa"}
        )

        self.assertEqual(resposta.status_code, 409)
        self.lazer.refresh_from_db()
        self.assertEqual(self.lazer.nome, "Lazer")

    def test_mesmo_nome_e_aceito_em_outro_tipo_ou_usuaria(self):
        outro_tipo = self.enviar("post", "/api/categorias", {"nome": "Mercado", "tipo": "receita"})
        outra_usuaria = self.enviar("post", "/api/categorias", {"nome": "Da Bia", "tipo": "despesa"})

        self.assertEqual(outro_tipo.status_code, 201)
        self.assertEqual(outra_usuaria.status_code, 201)

    def test_recusa_dados_invalidos(self):
        invalidos = [
            {},
            {"nome": "   ", "tipo": "despesa"},
            {"nome": "x" * 81, "tipo": "despesa"},
            {"nome": "Nova\x00", "tipo": "despesa"},
            {"nome": "Nova", "tipo": "transferencia"},
            {"nome": "Nova", "tipo": "receita", "essencial": True},
            {"nome": "Nova", "tipo": "despesa", "essencial": "sim"},
            {"nome": "Nova", "tipo": "despesa", "usuaria_id": self.bia.id},
        ]

        for dados in invalidos:
            with self.subTest(dados=dados):
                self.assertEqual(self.enviar("post", "/api/categorias", dados).status_code, 422)
        self.assertEqual(Categoria.objects.count(), 4)

    def test_exclui_categoria_sem_transacoes(self):
        resposta = self.client.delete(f"/api/categorias/{self.lazer.id}")

        self.assertEqual(resposta.status_code, 204)
        self.assertFalse(Categoria.objects.filter(id=self.lazer.id).exists())

    def test_nao_exclui_categoria_em_uso(self):
        self.transacao()

        resposta = self.client.delete(f"/api/categorias/{self.mercado.id}")

        self.assertEqual(resposta.status_code, 409)
        self.assertTrue(Categoria.objects.filter(id=self.mercado.id).exists())

    def test_tipo_so_muda_em_categoria_sem_transacoes(self):
        self.transacao()
        dados = {"nome": "Mudou", "tipo": "receita"}

        em_uso = self.enviar("put", f"/api/categorias/{self.mercado.id}", dados)
        livre = self.enviar("put", f"/api/categorias/{self.lazer.id}", dados)

        self.assertEqual(em_uso.status_code, 409)
        self.assertEqual(livre.status_code, 200)
        self.mercado.refresh_from_db()
        self.assertEqual(self.mercado.tipo, DESPESA)

    def test_listagem_retorna_somente_categorias_proprias(self):
        ids = {item["id"] for item in self.client.get("/api/categorias").json()}

        self.assertEqual(ids, {self.mercado.id, self.lazer.id, self.salario.id})

    def test_nao_acessa_categoria_de_outra_usuaria_por_id(self):
        url = f"/api/categorias/{self.da_bia.id}"
        dados = {"nome": "Invadida", "tipo": "despesa"}

        respostas = [
            self.client.get(url),
            self.enviar("put", url, dados),
            self.client.delete(url),
        ]

        self.assertEqual([r.status_code for r in respostas], [404] * 3)
        self.da_bia.refresh_from_db()
        self.assertEqual(self.da_bia.nome, "Da Bia")


class TransacaoTests(BaseTransacoes):
    def test_cria_despesa_para_a_usuaria_autenticada(self):
        resposta = self.enviar("post", "/api/transacoes", self.corpo(descricao=" Feira "))

        self.assertEqual(resposta.status_code, 201)
        corpo = resposta.json()
        self.assertEqual(corpo["valor"], "89.90")
        self.assertEqual(corpo["moeda"], "BRL")
        self.assertEqual(corpo["data"], "2026-03-10")
        self.assertEqual(corpo["descricao"], "Feira")
        self.assertEqual(corpo["categoria_nome"], "Mercado")
        self.assertIsNone(corpo["conta_id"])
        self.assertEqual(Transacao.objects.get(id=corpo["id"]).usuaria, self.ana)

    def test_cria_receita(self):
        resposta = self.enviar(
            "post",
            "/api/transacoes",
            self.corpo(tipo="receita", valor="3000", categoria_id=self.salario.id),
        )

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["valor"], "3000.00")

    def test_consulta_edita_e_exclui_transacao_propria(self):
        registro = self.transacao()
        url = f"/api/transacoes/{registro.id}"

        consultada = self.client.get(url)
        editada = self.enviar(
            "put",
            url,
            self.corpo(valor="20.05", data="2026-04-01", categoria_id=self.lazer.id),
        )
        excluida = self.client.delete(url)

        self.assertEqual(consultada.status_code, 200)
        self.assertEqual(editada.status_code, 200)
        self.assertEqual(editada.json()["valor"], "20.05")
        self.assertEqual(editada.json()["categoria_nome"], "Lazer")
        self.assertEqual(excluida.status_code, 204)
        self.assertFalse(Transacao.objects.filter(id=registro.id).exists())

    def test_valor_preserva_decimal_exato(self):
        casos = {"0.01": "0.01", "0.10": "0.10", "1234.5": "1234.50", "999999999999.99": "999999999999.99"}

        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                resposta = self.enviar("post", "/api/transacoes", self.corpo(valor=entrada))
                self.assertEqual(resposta.status_code, 201)
                self.assertEqual(resposta.json()["valor"], esperado)
                registro = Transacao.objects.get(id=resposta.json()["id"])
                self.assertEqual(registro.valor, Decimal(esperado))

    def test_recusa_valor_invalido(self):
        invalidos = [
            10.5, 10, None, True, "", "0", "0.00", "-1.00", "abc", "10,50", "1.234",
            "1e3", "NaN", "Infinity", " 10.00", "10.00\n", "١٠", "1000000000000.00", "89.901",
        ]

        for valor in invalidos:
            with self.subTest(valor=valor):
                resposta = self.enviar("post", "/api/transacoes", self.corpo(valor=valor))
                self.assertEqual(resposta.status_code, 422)
        self.assertFalse(Transacao.objects.exists())

    def test_recusa_data_invalida(self):
        amanha = timezone.localdate() + timedelta(days=1)
        invalidas = [
            None, 1700000000, 1773100800, "1773100800", "", "10/03/2026", "2026-3-10",
            "2026-02-30", "2026-03-10T10:00:00", "2026-03-10T00:00:00", amanha.isoformat(),
        ]

        for data in invalidas:
            with self.subTest(data=data):
                resposta = self.enviar("post", "/api/transacoes", self.corpo(data=data))
                self.assertEqual(resposta.status_code, 422)
        self.assertFalse(Transacao.objects.exists())

    def test_aceita_a_data_de_hoje(self):
        hoje = timezone.localdate().isoformat()

        self.assertEqual(self.enviar("post", "/api/transacoes", self.corpo(data=hoje)).status_code, 201)

    def test_recusa_demais_campos_invalidos(self):
        invalidos = [
            self.corpo(tipo="transferencia"),
            self.corpo(categoria_id=True),
            self.corpo(categoria_id=str(self.mercado.id)),
            self.corpo(categoria_id=None),
            self.corpo(conta_id="1"),
            self.corpo(descricao="x" * 201),
            self.corpo(descricao="Feira\x00"),
            self.corpo(descricao=None),
            self.corpo(moeda="USD"),
            self.corpo(usuaria_id=self.bia.id),
        ]

        for dados in invalidos:
            with self.subTest(dados=dados):
                self.assertEqual(self.enviar("post", "/api/transacoes", dados).status_code, 422)
        self.assertFalse(Transacao.objects.exists())

    def test_tipo_precisa_corresponder_a_categoria(self):
        resposta = self.enviar("post", "/api/transacoes", self.corpo(tipo="receita"))

        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(resposta.json()["detail"][0]["loc"][-1], "categoria_id")
        self.assertFalse(Transacao.objects.exists())

    def test_vincula_conta_propria_sem_alterar_saldo_declarado(self):
        conta = ContaManual.objects.create(
            usuaria=self.ana, nome="Principal", tipo="corrente", saldo_declarado=Decimal("500.00")
        )

        resposta = self.enviar("post", "/api/transacoes", self.corpo(conta_id=conta.id))

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["conta_id"], conta.id)
        conta.refresh_from_db()
        self.assertEqual(conta.saldo_declarado, Decimal("500.00"))

    def test_edicao_invalida_nao_altera_a_transacao(self):
        registro = self.transacao()

        resposta = self.enviar(
            "put", f"/api/transacoes/{registro.id}", self.corpo(valor="0", descricao="Alterada")
        )

        self.assertEqual(resposta.status_code, 422)
        registro.refresh_from_db()
        self.assertEqual(registro.valor, Decimal("10.00"))
        self.assertEqual(registro.descricao, "")

    def test_banco_recusa_valor_nao_positivo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.transacao(valor=Decimal("0.00"))

    def test_banco_recusa_receita_essencial(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Categoria.objects.create(usuaria=self.ana, nome="Bônus", tipo=RECEITA, essencial=True)

    def test_remover_usuaria_remove_seus_registros(self):
        self.transacao()

        self.ana.delete()

        self.assertFalse(Transacao.objects.exists())
        self.assertFalse(Categoria.objects.filter(usuaria_id=self.mercado.usuaria_id).exists())


class FiltrosTests(BaseTransacoes):
    def setUp(self):
        super().setUp()
        self.jan = self.transacao(valor=Decimal("100.10"), data=date(2026, 1, 31))
        self.fev = self.transacao(
            categoria=self.lazer, valor=Decimal("50.20"), data=date(2026, 2, 1)
        )
        self.mar = self.transacao(valor=Decimal("0.30"), data=date(2026, 3, 1))
        self.renda = self.transacao(
            categoria=self.salario, valor=Decimal("3000.00"), data=date(2026, 2, 5)
        )
        self.transacao(
            usuaria=self.bia, categoria=self.da_bia, valor=Decimal("777.77"), data=date(2026, 2, 2)
        )

    def listar(self, consulta=""):
        return self.client.get(f"/api/transacoes{consulta}")

    def ids(self, consulta=""):
        return [item["id"] for item in self.listar(consulta).json()["itens"]]

    def test_lista_da_data_mais_recente_para_a_mais_antiga(self):
        self.assertEqual(self.ids(), [self.mar.id, self.renda.id, self.fev.id, self.jan.id])

    def test_totais_usam_decimal_exato_e_identificam_moeda(self):
        corpo = self.listar().json()

        self.assertEqual(corpo["moeda"], "BRL")
        self.assertEqual(corpo["quantidade"], 4)
        self.assertEqual(
            corpo["totais"],
            {"receitas": "3000.00", "despesas": "150.60", "resultado": "2849.40"},
        )

    def test_periodo_inclui_as_duas_datas_limite(self):
        corpo = self.listar("?data_inicio=2026-01-31&data_fim=2026-02-01").json()

        self.assertEqual([item["id"] for item in corpo["itens"]], [self.fev.id, self.jan.id])
        self.assertEqual(corpo["periodo"], {"inicio": "2026-01-31", "fim": "2026-02-01"})
        self.assertEqual(corpo["totais"]["despesas"], "150.30")

    def test_filtra_por_inicio_ou_fim_isoladamente(self):
        self.assertEqual(self.ids("?data_inicio=2026-03-01"), [self.mar.id])
        self.assertEqual(self.ids("?data_fim=2026-01-31"), [self.jan.id])

    def test_filtra_por_categoria(self):
        corpo = self.listar(f"?categoria_id={self.mercado.id}").json()

        self.assertEqual([item["id"] for item in corpo["itens"]], [self.mar.id, self.jan.id])
        self.assertEqual(corpo["totais"]["despesas"], "100.40")
        self.assertEqual(corpo["totais"]["receitas"], "0.00")

    def test_filtra_por_tipo(self):
        self.assertEqual(self.ids("?tipo=receita"), [self.renda.id])

    def test_combina_periodo_e_categoria(self):
        consulta = f"?data_inicio=2026-02-01&data_fim=2026-03-31&categoria_id={self.mercado.id}"

        self.assertEqual(self.ids(consulta), [self.mar.id])

    def test_filtro_sem_resultados_retorna_totais_zerados(self):
        corpo = self.listar("?data_inicio=2020-01-01&data_fim=2020-12-31").json()

        self.assertEqual(corpo["itens"], [])
        self.assertEqual(corpo["quantidade"], 0)
        self.assertEqual(
            corpo["totais"], {"receitas": "0.00", "despesas": "0.00", "resultado": "0.00"}
        )

    def test_paginacao_nao_altera_os_totais(self):
        corpo = self.listar("?limite=1&deslocamento=1").json()

        self.assertEqual([item["id"] for item in corpo["itens"]], [self.renda.id])
        self.assertEqual(corpo["quantidade"], 4)
        self.assertEqual(corpo["limite"], 1)
        self.assertEqual(corpo["deslocamento"], 1)
        self.assertEqual(corpo["totais"]["despesas"], "150.60")

    def test_recusa_filtros_invalidos(self):
        consultas = [
            "?data_inicio=2026-03-02&data_fim=2026-03-01",
            "?data_inicio=01/03/2026",
            "?data_fim=2026-02-30",
            "?data_inicio=",
            "?categoria_id=abc",
            "?categoria_id=0",
            "?tipo=transferencia",
            "?limite=0",
            "?limite=201",
            "?deslocamento=-1",
            f"?deslocamento={10**30}",
            "?categoria=1",
        ]

        for consulta in consultas:
            with self.subTest(consulta=consulta):
                self.assertEqual(self.listar(consulta).status_code, 422)


class IsolamentoDeTransacoesTests(BaseTransacoes):
    def setUp(self):
        super().setUp()
        self.conta_bia = ContaManual.objects.create(
            usuaria=self.bia, nome="Conta da Bia", tipo="corrente", saldo_declarado=Decimal("1.00")
        )
        self.minha = self.transacao(valor=Decimal("10.00"))
        self.alheia = self.transacao(
            usuaria=self.bia, categoria=self.da_bia, valor=Decimal("777.77"), descricao="Da Bia"
        )

    def test_listagem_e_totais_ignoram_registros_de_outra_usuaria(self):
        corpo = self.client.get("/api/transacoes").json()

        self.assertEqual([item["id"] for item in corpo["itens"]], [self.minha.id])
        self.assertEqual(corpo["totais"]["despesas"], "10.00")

    def test_filtro_por_categoria_alheia_nao_retorna_dados(self):
        corpo = self.client.get(f"/api/transacoes?categoria_id={self.da_bia.id}").json()

        self.assertEqual(corpo["itens"], [])
        self.assertEqual(corpo["totais"]["despesas"], "0.00")

    def test_nao_consulta_transacao_de_outra_usuaria_por_id(self):
        alheia = self.client.get(f"/api/transacoes/{self.alheia.id}")
        inexistente = self.client.get(f"/api/transacoes/{self.alheia.id + 1000}")

        self.assertEqual(alheia.status_code, 404)
        self.assertEqual(alheia.content, inexistente.content)

    def test_nao_edita_transacao_de_outra_usuaria_por_id(self):
        resposta = self.enviar("put", f"/api/transacoes/{self.alheia.id}", self.corpo())

        self.assertEqual(resposta.status_code, 404)
        self.alheia.refresh_from_db()
        self.assertEqual(self.alheia.valor, Decimal("777.77"))
        self.assertEqual(self.alheia.categoria, self.da_bia)

    def test_nao_exclui_transacao_de_outra_usuaria_por_id(self):
        resposta = self.client.delete(f"/api/transacoes/{self.alheia.id}")

        self.assertEqual(resposta.status_code, 404)
        self.assertTrue(Transacao.objects.filter(id=self.alheia.id).exists())

    def test_categoria_alheia_e_inexistente_tem_a_mesma_resposta(self):
        alheia = self.enviar("post", "/api/transacoes", self.corpo(categoria_id=self.da_bia.id))
        inexistente = self.enviar(
            "post", "/api/transacoes", self.corpo(categoria_id=self.da_bia.id + 1000)
        )

        self.assertEqual(alheia.status_code, 422)
        self.assertEqual(alheia.content, inexistente.content)
        self.assertEqual(Transacao.objects.count(), 2)

    def test_conta_alheia_e_inexistente_tem_a_mesma_resposta(self):
        alheia = self.enviar("post", "/api/transacoes", self.corpo(conta_id=self.conta_bia.id))
        inexistente = self.enviar(
            "post", "/api/transacoes", self.corpo(conta_id=self.conta_bia.id + 1000)
        )

        self.assertEqual(alheia.status_code, 422)
        self.assertEqual(alheia.content, inexistente.content)
        self.assertEqual(Transacao.objects.count(), 2)

    def test_edicao_nao_vincula_categoria_ou_conta_alheia(self):
        url = f"/api/transacoes/{self.minha.id}"

        categoria = self.enviar("put", url, self.corpo(categoria_id=self.da_bia.id))
        conta = self.enviar("put", url, self.corpo(conta_id=self.conta_bia.id))

        self.assertEqual(categoria.status_code, 422)
        self.assertEqual(conta.status_code, 422)
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.categoria, self.mercado)
        self.assertIsNone(self.minha.conta)

    def test_sem_sessao_nenhuma_operacao_acessa_ou_modifica_dados(self):
        anonimo = Client()
        url = f"/api/transacoes/{self.minha.id}"
        categoria = f"/api/categorias/{self.mercado.id}"
        dados_categoria = {"nome": "Anônima", "tipo": "despesa"}

        respostas = [
            anonimo.get("/api/transacoes"),
            self.enviar("post", "/api/transacoes", self.corpo(), anonimo),
            anonimo.get(url),
            self.enviar("put", url, self.corpo(valor="1.00"), anonimo),
            anonimo.delete(url),
            anonimo.get("/api/categorias"),
            self.enviar("post", "/api/categorias", dados_categoria, anonimo),
            anonimo.get(categoria),
            self.enviar("put", categoria, dados_categoria, anonimo),
            anonimo.delete(categoria),
        ]

        self.assertEqual([r.status_code for r in respostas], [401] * 10)
        self.minha.refresh_from_db()
        self.assertEqual(self.minha.valor, Decimal("10.00"))
        self.assertEqual(Transacao.objects.count(), 2)
        self.assertEqual(Categoria.objects.count(), 4)

    def test_escrita_sem_token_csrf_e_recusada(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.ana)

        respostas = [
            self.enviar("post", "/api/transacoes", self.corpo(), cliente),
            cliente.delete(f"/api/transacoes/{self.minha.id}"),
            self.enviar("post", "/api/categorias", {"nome": "X", "tipo": "despesa"}, cliente),
        ]

        self.assertEqual([r.status_code for r in respostas], [403] * 3)
        self.assertEqual(Transacao.objects.count(), 2)


CONTRATO = settings.BASE_DIR.parent.parent / "contracts" / "openapi.json"


class TotaisNoContratoTests(BaseTransacoes):
    """Revisão do PR #127: os totais não podem usar o formato do valor individual."""

    def padrao_publicado(self, campo):
        esquemas = json.loads(CONTRATO.read_text(encoding="utf-8"))["components"]["schemas"]
        return esquemas["TotaisOut"]["properties"][campo]["pattern"]

    def test_total_acima_de_12_digitos_respeita_o_contrato_publicado(self):
        for _ in range(2):
            self.transacao(categoria=self.salario, valor=Decimal("600000000000.00"))
        self.transacao(valor=Decimal("999999999999.99"))

        totais = self.client.get("/api/transacoes").json()["totais"]

        self.assertEqual(totais, {"receitas": "1200000000000.00", "despesas": "999999999999.99",
                                  "resultado": "200000000000.01"})
        for campo, valor in totais.items():
            with self.subTest(campo=campo):
                self.assertRegex(valor, self.padrao_publicado(campo))

    def test_total_negativo_e_zero_respeitam_o_contrato_publicado(self):
        self.transacao(valor=Decimal("600000000000.00"))
        self.transacao(valor=Decimal("600000000000.00"))

        totais = self.client.get("/api/transacoes").json()["totais"]

        self.assertEqual(totais["resultado"], "-1200000000000.00")
        self.assertEqual(totais["receitas"], "0.00")
        for campo, valor in totais.items():
            self.assertRegex(valor, self.padrao_publicado(campo))

    def test_pagina_vazia_mantem_os_totais_do_filtro(self):
        self.transacao(valor=Decimal("10.00"))
        self.transacao(valor=Decimal("5.50"))

        corpo = self.client.get("/api/transacoes?deslocamento=10").json()

        self.assertEqual(corpo["itens"], [])
        self.assertEqual((corpo["quantidade"], corpo["totais"]["despesas"]), (2, "15.50"))


class ConflitoDeNomeDeCategoriaTests(BaseTransacoes):
    def test_outra_restricao_unica_nao_vira_nome_duplicado(self):
        # Revisão do PR #127: só a restrição de nome único da categoria responde 409.
        def viola_conta_unica(*args, **kwargs):
            for _ in range(2):
                ContaManual.objects.create(usuaria=self.ana, nome="Repetida", tipo="corrente",
                                           saldo_declarado=Decimal("0.00"))

        cliente = Client(raise_request_exception=False)
        cliente.force_login(self.ana)
        with mock.patch.object(Categoria, "save", viola_conta_unica):
            resposta = self.enviar("post", "/api/categorias", {"nome": "Nova", "tipo": "despesa"}, cliente)

        self.assertEqual(resposta.status_code, 500)

    def test_nome_repetido_continua_respondendo_409(self):
        resposta = self.enviar("post", "/api/categorias", {"nome": "mercado", "tipo": "despesa"})

        self.assertEqual(resposta.status_code, 409)


class ListagemConsistenteTests(TransactionTestCase):
    """Revisão do PR #127: itens e totais saem do mesmo estado do banco.

    Uma transação é gravada, por outra conexão, logo depois da primeira leitura
    da tabela feita pela listagem. Com duas consultas (totais e depois itens), a
    segunda já enxergaria o registro novo e a resposta ficaria incoerente.
    """

    def setUp(self):
        Usuaria = get_user_model()
        self.ana = Usuaria.objects.create_user("ana.ficticia")
        self.mercado = Categoria.objects.create(usuaria=self.ana, nome="Mercado", tipo=DESPESA)
        for valor in ("10.00", "20.00"):
            Transacao.objects.create(usuaria=self.ana, categoria=self.mercado, tipo=DESPESA,
                                     valor=Decimal(valor), data=date(2026, 3, 10))
        self.client.force_login(self.ana)

    def gravar_por_outra_conexao(self):
        def gravar():
            try:
                Transacao.objects.create(usuaria=self.ana, categoria=self.mercado, tipo=DESPESA,
                                         valor=Decimal("1000.00"), data=date(2026, 3, 11))
            finally:
                connections.close_all()

        tarefa = threading.Thread(target=gravar)
        tarefa.start()
        tarefa.join()

    def listar_com_escrita_concorrente(self, consulta=""):
        """Lista e grava uma transação por outra conexão logo após a primeira leitura."""
        gravou = []

        def depois_da_primeira_leitura(execute, sql, params, many, context):
            resultado = execute(sql, params, many, context)
            if not gravou and sql.lstrip().upper().startswith("SELECT") and '"financas_transacao"' in sql:
                gravou.append(True)
                self.gravar_por_outra_conexao()
            return resultado

        with connection.execute_wrapper(depois_da_primeira_leitura):
            corpo = self.client.get(f"/api/transacoes{consulta}").json()
        self.assertTrue(gravou)
        return corpo

    def test_escrita_concorrente_nao_separa_itens_e_totais(self):
        corpo = self.listar_com_escrita_concorrente()

        soma_dos_itens = sum(Decimal(item["valor"]) for item in corpo["itens"])
        self.assertEqual(corpo["quantidade"], len(corpo["itens"]))
        self.assertEqual(Decimal(corpo["totais"]["despesas"]), soma_dos_itens)
        self.assertEqual(Transacao.objects.count(), 3)

    def test_pagina_vazia_e_totais_veem_o_mesmo_estado(self):
        # Revisão do PR #127: com dois registros e deslocamento=2, a página vem
        # vazia e os totais exigem uma segunda consulta. A inserção entre as duas
        # não pode aparecer na quantidade nem nos totais.
        corpo = self.listar_com_escrita_concorrente("?deslocamento=2")

        self.assertEqual(corpo["itens"], [])
        self.assertEqual(corpo["quantidade"], 2)
        self.assertEqual(corpo["totais"]["despesas"], "30.00")
        self.assertEqual(Transacao.objects.count(), 3)

    def test_listagem_seguinte_ve_a_escrita_concorrente(self):
        self.listar_com_escrita_concorrente("?deslocamento=2")

        corpo = self.client.get("/api/transacoes").json()

        self.assertEqual((corpo["quantidade"], corpo["totais"]["despesas"]), (3, "1030.00"))
