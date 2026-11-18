from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from financas.models import (
    Categoria,
    MovimentacaoReserva,
    ReservaEmergencia,
    TipoLancamento,
    Transacao,
)
from financas.reserva import (
    arredondar,
    avaliar_reserva,
    calcular_media_mensal,
    calcular_meta,
    calcular_progresso,
    calcular_saldo,
    contar_meses,
    somar_meses,
)

JSON = "application/json"
HOJE = date(2026, 11, 18)
APORTE = MovimentacaoReserva.Tipo.APORTE
RETIRADA = MovimentacaoReserva.Tipo.RETIRADA


class CalculosTests(SimpleTestCase):
    def test_meta_multiplica_despesas_mensais_por_meses_de_cobertura(self):
        self.assertEqual(calcular_meta(Decimal("2000.00"), 3), Decimal("6000.00"))

    def test_saldo_soma_aportes_e_subtrai_retiradas(self):
        saldo = calcular_saldo(Decimal("500.00"), Decimal("200.00"), Decimal("100.00"))

        self.assertEqual(saldo, Decimal("600.00"))

    def test_progresso_do_exemplo_de_referencia(self):
        self.assertEqual(calcular_progresso(Decimal("600.00"), Decimal("6000.00")), Decimal("10.00"))

    def test_progresso_nao_e_calculado_com_meta_zero(self):
        self.assertIsNone(calcular_progresso(Decimal("600.00"), Decimal("0.00")))

    def test_progresso_pode_superar_cem_por_cento(self):
        self.assertEqual(calcular_progresso(Decimal("150.00"), Decimal("100.00")), Decimal("150.00"))

    def test_arredonda_a_metade_para_cima(self):
        casos = {
            "10.125": "10.13",
            "10.135": "10.14",
            "10.124": "10.12",
            "0.005": "0.01",
        }

        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(str(arredondar(Decimal(entrada))), esperado)

    def test_progresso_arredonda_a_metade_para_cima(self):
        self.assertEqual(calcular_progresso(Decimal("1.00"), Decimal("800.00")), Decimal("0.13"))

    def test_media_mensal_usa_duas_casas(self):
        self.assertEqual(calcular_media_mensal(Decimal("100.00"), 3), Decimal("33.33"))
        self.assertEqual(calcular_media_mensal(Decimal("200.00"), 3), Decimal("66.67"))

    def test_media_sem_meses_registrados_e_insuficiente(self):
        self.assertIsNone(calcular_media_mensal(Decimal("0.00"), 0))

    def test_meta_parte_da_media_exibida(self):
        media = calcular_media_mensal(Decimal("100.00"), 3)

        self.assertEqual(calcular_meta(media, 3), Decimal("99.99"))

    def test_avalia_reserva_completa(self):
        resultado = avaliar_reserva(Decimal("2000.00"), 3, Decimal("600.00"))

        self.assertEqual(resultado.estado, "calculado")
        self.assertEqual(resultado.faltando, [])
        self.assertEqual(resultado.meta, Decimal("6000.00"))
        self.assertEqual(resultado.progresso_percentual, Decimal("10.00"))

    def test_avalia_meta_zero_sem_dividir_por_zero(self):
        resultado = avaliar_reserva(Decimal("0.00"), 3, Decimal("600.00"))

        self.assertEqual(resultado.estado, "meta_zero")
        self.assertEqual(resultado.meta, Decimal("0.00"))
        self.assertIsNone(resultado.progresso_percentual)

    def test_avalia_cada_informacao_ausente(self):
        casos = [
            ((None, 3, Decimal("1.00")), ["despesas_essenciais"]),
            ((Decimal("1.00"), None, Decimal("1.00")), ["meses_cobertura"]),
            ((Decimal("1.00"), 3, None), ["saldo_inicial"]),
            ((None, None, None), ["despesas_essenciais", "meses_cobertura", "saldo_inicial"]),
        ]

        for argumentos, faltando in casos:
            with self.subTest(faltando=faltando):
                resultado = avaliar_reserva(*argumentos)
                self.assertEqual(resultado.estado, "dados_insuficientes")
                self.assertEqual(resultado.faltando, faltando)
                self.assertIsNone(resultado.progresso_percentual)

    def test_desloca_meses_entre_anos(self):
        self.assertEqual(somar_meses(date(2026, 1, 1), -1), date(2025, 12, 1))
        self.assertEqual(somar_meses(date(2026, 12, 1), 1), date(2027, 1, 1))
        self.assertEqual(somar_meses(date(2026, 11, 1), -3), date(2026, 8, 1))

    def test_conta_meses_incluindo_os_limites(self):
        self.assertEqual(contar_meses(date(2026, 8, 1), date(2026, 10, 1)), 3)
        self.assertEqual(contar_meses(date(2025, 12, 1), date(2026, 1, 1)), 2)


class BaseReserva(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuaria = get_user_model()
        cls.ana = Usuaria.objects.create_user("ana.ficticia")
        cls.bia = Usuaria.objects.create_user("bia.ficticia")
        cls.essencial = Categoria.objects.create(
            usuaria=cls.ana, nome="Moradia", tipo=TipoLancamento.DESPESA, essencial=True
        )
        cls.comum = Categoria.objects.create(
            usuaria=cls.ana, nome="Lazer", tipo=TipoLancamento.DESPESA
        )
        cls.receita = Categoria.objects.create(
            usuaria=cls.ana, nome="Salário", tipo=TipoLancamento.RECEITA
        )
        cls.essencial_bia = Categoria.objects.create(
            usuaria=cls.bia, nome="Moradia", tipo=TipoLancamento.DESPESA, essencial=True
        )

    def setUp(self):
        self.client.force_login(self.ana)
        relogio = mock.patch("django.utils.timezone.localdate", return_value=HOJE)
        relogio.start()
        self.addCleanup(relogio.stop)

    def enviar(self, metodo, url, dados, cliente=None):
        return getattr(cliente or self.client, metodo)(url, dados, content_type=JSON)

    def despesa(self, valor, data, categoria=None, usuaria=None):
        categoria = categoria or self.essencial
        return Transacao.objects.create(
            usuaria=usuaria or self.ana,
            categoria=categoria,
            tipo=categoria.tipo,
            valor=Decimal(valor),
            data=data,
        )

    def reserva(self, saldo_inicial="500.00", meses=3, usuaria=None):
        return ReservaEmergencia.objects.create(
            usuaria=usuaria or self.ana,
            saldo_inicial=Decimal(saldo_inicial),
            meses_cobertura=meses,
        )

    def movimentacao(self, tipo, valor, usuaria=None, data=date(2026, 10, 1)):
        return MovimentacaoReserva.objects.create(
            usuaria=usuaria or self.ana, tipo=tipo, valor=Decimal(valor), data=data
        )

    def resumo(self, consulta=""):
        return self.client.get(f"/api/reserva{consulta}")


class ConfiguracaoTests(BaseReserva):
    def test_cria_e_edita_a_propria_reserva(self):
        criada = self.enviar(
            "put", "/api/reserva", {"saldo_inicial": "500", "meses_cobertura": 6}
        )
        editada = self.enviar(
            "put", "/api/reserva", {"saldo_inicial": "750.50", "meses_cobertura": 12}
        )

        self.assertEqual(criada.status_code, 201)
        self.assertEqual(criada.json()["saldo_inicial"], "500.00")
        self.assertEqual(editada.status_code, 200)
        self.assertEqual(editada.json()["saldo_inicial"], "750.50")
        self.assertEqual(editada.json()["moeda"], "BRL")
        self.assertEqual(ReservaEmergencia.objects.get().usuaria, self.ana)

    def test_aceita_limites_de_cobertura_e_cobertura_ausente(self):
        for meses in (1, 60, None):
            with self.subTest(meses=meses):
                resposta = self.enviar(
                    "put", "/api/reserva", {"saldo_inicial": "0.00", "meses_cobertura": meses}
                )
                self.assertIn(resposta.status_code, (200, 201))
                self.assertEqual(resposta.json()["meses_cobertura"], meses)

    def test_recusa_dados_invalidos(self):
        invalidos = [
            {},
            {"saldo_inicial": 500, "meses_cobertura": 3},
            {"saldo_inicial": "-1.00", "meses_cobertura": 3},
            {"saldo_inicial": "1.234", "meses_cobertura": 3},
            {"saldo_inicial": "abc", "meses_cobertura": 3},
            {"saldo_inicial": "500.00", "meses_cobertura": 0},
            {"saldo_inicial": "500.00", "meses_cobertura": 61},
            {"saldo_inicial": "500.00", "meses_cobertura": 1.5},
            {"saldo_inicial": "500.00", "meses_cobertura": "3"},
            {"saldo_inicial": "500.00", "meses_cobertura": True},
            {"saldo_inicial": "500.00", "usuaria_id": self.bia.id},
            {"saldo_inicial": "500.00", "moeda": "USD"},
        ]

        for dados in invalidos:
            with self.subTest(dados=dados):
                self.assertEqual(self.enviar("put", "/api/reserva", dados).status_code, 422)
        self.assertFalse(ReservaEmergencia.objects.exists())

    def test_reducao_do_saldo_inicial_nao_pode_negativar_a_reserva(self):
        self.reserva("500.00")
        self.movimentacao(RETIRADA, "400.00")

        recusada = self.enviar("put", "/api/reserva", {"saldo_inicial": "399.99"})
        aceita = self.enviar("put", "/api/reserva", {"saldo_inicial": "400.00"})

        self.assertEqual(recusada.status_code, 409)
        self.assertEqual(aceita.status_code, 200)

    def test_banco_recusa_configuracao_invalida(self):
        for campos in ({"saldo_inicial": "-1.00"}, {"meses": 61}, {"meses": 0}):
            with self.subTest(campos=campos), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self.reserva(**campos)


class ResumoTests(BaseReserva):
    def test_calcula_o_exemplo_de_referencia(self):
        self.despesa("2000.00", date(2026, 10, 10))
        self.reserva("500.00", meses=3)
        self.movimentacao(APORTE, "200.00")
        self.movimentacao(RETIRADA, "100.00")

        corpo = self.resumo().json()

        self.assertEqual(corpo["estado"], "calculado")
        self.assertEqual(corpo["faltando"], [])
        self.assertEqual(corpo["moeda"], "BRL")
        self.assertEqual(corpo["despesas_essenciais_mensais"], "2000.00")
        self.assertEqual(corpo["meses_cobertura"], 3)
        self.assertEqual(corpo["meta"], "6000.00")
        self.assertEqual(corpo["saldo_inicial"], "500.00")
        self.assertEqual(corpo["aportes"], "200.00")
        self.assertEqual(corpo["retiradas"], "100.00")
        self.assertEqual(corpo["saldo_declarado"], "600.00")
        self.assertEqual(corpo["progresso_percentual"], "10.00")

    def test_sem_filtros_usa_os_tres_ultimos_meses_completos(self):
        self.despesa("9000.00", date(2026, 7, 31))
        self.despesa("100.00", date(2026, 8, 1))
        self.despesa("200.00", date(2026, 9, 15))
        self.despesa("300.00", date(2026, 10, 31))
        self.despesa("9000.00", date(2026, 11, 1))

        corpo = self.resumo().json()

        self.assertEqual(
            corpo["periodo"],
            {
                "mes_inicio": "2026-08",
                "mes_fim": "2026-10",
                "meses_no_periodo": 3,
                "meses_com_registro": 3,
            },
        )
        self.assertEqual(corpo["despesas_essenciais_total"], "600.00")
        self.assertEqual(corpo["despesas_essenciais_mensais"], "200.00")

    def test_filtra_pelo_periodo_informado(self):
        self.despesa("100.00", date(2026, 1, 31))
        self.despesa("300.00", date(2026, 2, 1))
        self.despesa("500.00", date(2026, 3, 31))
        self.despesa("700.00", date(2026, 4, 1))

        corpo = self.resumo("?mes_inicio=2026-02&mes_fim=2026-03").json()

        self.assertEqual(corpo["periodo"]["mes_inicio"], "2026-02")
        self.assertEqual(corpo["periodo"]["mes_fim"], "2026-03")
        self.assertEqual(corpo["despesas_essenciais_total"], "800.00")
        self.assertEqual(corpo["despesas_essenciais_mensais"], "400.00")

    def test_periodo_de_um_mes_e_entre_anos(self):
        self.despesa("100.00", date(2025, 12, 31))
        self.despesa("300.00", date(2026, 1, 1))

        um_mes = self.resumo("?mes_inicio=2026-01&mes_fim=2026-01").json()
        entre_anos = self.resumo("?mes_inicio=2025-12&mes_fim=2026-01").json()

        self.assertEqual(um_mes["despesas_essenciais_mensais"], "300.00")
        self.assertEqual(entre_anos["despesas_essenciais_mensais"], "200.00")

    def test_mes_sem_registro_nao_entra_na_media(self):
        self.despesa("300.00", date(2026, 8, 10))
        self.despesa("100.00", date(2026, 10, 10))

        corpo = self.resumo().json()

        self.assertEqual(corpo["periodo"]["meses_no_periodo"], 3)
        self.assertEqual(corpo["periodo"]["meses_com_registro"], 2)
        self.assertEqual(corpo["despesas_essenciais_mensais"], "200.00")

    def test_varias_despesas_no_mesmo_mes_contam_um_mes(self):
        self.despesa("100.00", date(2026, 10, 1))
        self.despesa("150.00", date(2026, 10, 2))

        corpo = self.resumo().json()

        self.assertEqual(corpo["periodo"]["meses_com_registro"], 1)
        self.assertEqual(corpo["despesas_essenciais_mensais"], "250.00")

    def test_considera_somente_despesas_essenciais_da_usuaria(self):
        self.despesa("100.00", date(2026, 10, 1))
        self.despesa("900.00", date(2026, 10, 1), categoria=self.comum)
        self.despesa("900.00", date(2026, 10, 1), categoria=self.receita)
        self.despesa("900.00", date(2026, 10, 1), categoria=self.essencial_bia, usuaria=self.bia)

        self.assertEqual(self.resumo().json()["despesas_essenciais_total"], "100.00")

    def test_saldo_ignora_movimentacoes_de_outra_usuaria(self):
        self.reserva("500.00")
        self.reserva("1.00", usuaria=self.bia)
        self.movimentacao(APORTE, "777.00", usuaria=self.bia)

        corpo = self.resumo().json()

        self.assertEqual(corpo["aportes"], "0.00")
        self.assertEqual(corpo["saldo_declarado"], "500.00")

    def test_arredonda_a_media_antes_de_calcular_a_meta(self):
        self.despesa("100.00", date(2026, 8, 1))
        self.despesa("100.00", date(2026, 9, 1))
        self.despesa("0.01", date(2026, 10, 1))
        self.reserva("0.00", meses=3)

        corpo = self.resumo().json()

        self.assertEqual(corpo["despesas_essenciais_mensais"], "66.67")
        self.assertEqual(corpo["meta"], "200.01")

    def test_sem_nenhum_dado_informa_tudo_que_falta(self):
        corpo = self.resumo().json()

        self.assertEqual(corpo["estado"], "dados_insuficientes")
        self.assertEqual(
            corpo["faltando"], ["despesas_essenciais", "meses_cobertura", "saldo_inicial"]
        )
        self.assertEqual(corpo["despesas_essenciais_total"], "0.00")
        self.assertIsNone(corpo["despesas_essenciais_mensais"])
        self.assertIsNone(corpo["saldo_declarado"])
        self.assertIsNone(corpo["meta"])
        self.assertIsNone(corpo["progresso_percentual"])

    def test_sem_cobertura_informa_o_campo_ausente(self):
        self.despesa("100.00", date(2026, 10, 1))
        self.reserva("500.00", meses=None)

        corpo = self.resumo().json()

        self.assertEqual(corpo["estado"], "dados_insuficientes")
        self.assertEqual(corpo["faltando"], ["meses_cobertura"])
        self.assertEqual(corpo["saldo_declarado"], "500.00")
        self.assertIsNone(corpo["meta"])

    def test_sem_despesas_no_periodo_nao_inventa_meta(self):
        self.despesa("100.00", date(2026, 1, 1))
        self.reserva("500.00")

        corpo = self.resumo().json()

        self.assertEqual(corpo["estado"], "dados_insuficientes")
        self.assertEqual(corpo["faltando"], ["despesas_essenciais"])

    def test_recusa_filtros_invalidos(self):
        consultas = [
            "?mes_inicio=2026-08",
            "?mes_fim=2026-08",
            "?mes_inicio=2026-09&mes_fim=2026-08",
            "?mes_inicio=2026-13&mes_fim=2026-13",
            "?mes_inicio=2026-00&mes_fim=2026-08",
            "?mes_inicio=08/2026&mes_fim=09/2026",
            "?mes_inicio=2026-8&mes_fim=2026-9",
            "?mes_inicio=2026-08-01&mes_fim=2026-09-01",
            "?mes_inicio=&mes_fim=",
            "?mes_inicio=2026-10&mes_fim=2026-11",
            "?mes_inicio=2026-12&mes_fim=2026-12",
            "?mes_inicio=2024-10&mes_fim=2026-10",
            "?inicio=2026-08",
        ]

        for consulta in consultas:
            with self.subTest(consulta=consulta):
                self.assertEqual(self.resumo(consulta).status_code, 422)

    def test_aceita_periodo_maximo_ate_o_ultimo_mes_completo(self):
        self.assertEqual(self.resumo("?mes_inicio=2024-11&mes_fim=2026-10").status_code, 200)


class MovimentacaoTests(BaseReserva):
    def corpo(self, **campos):
        return {"tipo": "aporte", "valor": "200.00", "data": "2026-10-10", **campos}

    def test_registra_aporte_e_retirada(self):
        self.reserva("500.00")

        aporte = self.enviar(
            "post", "/api/reserva/movimentacoes", self.corpo(descricao=" Depósito ")
        )
        retirada = self.enviar(
            "post", "/api/reserva/movimentacoes", self.corpo(tipo="retirada", valor="100")
        )

        self.assertEqual(aporte.status_code, 201)
        self.assertEqual(aporte.json()["descricao"], "Depósito")
        self.assertEqual(aporte.json()["moeda"], "BRL")
        self.assertEqual(retirada.status_code, 201)
        self.assertEqual(retirada.json()["valor"], "100.00")
        self.assertEqual(self.resumo().json()["saldo_declarado"], "600.00")

    def test_exige_reserva_configurada(self):
        resposta = self.enviar("post", "/api/reserva/movimentacoes", self.corpo())

        self.assertEqual(resposta.status_code, 409)
        self.assertFalse(MovimentacaoReserva.objects.exists())

    def test_retirada_pode_usar_todo_o_saldo(self):
        self.reserva("100.00")

        resposta = self.enviar(
            "post", "/api/reserva/movimentacoes", self.corpo(tipo="retirada", valor="100.00")
        )

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(self.resumo().json()["saldo_declarado"], "0.00")

    def test_recusa_retirada_acima_do_saldo(self):
        self.reserva("100.00")

        resposta = self.enviar(
            "post", "/api/reserva/movimentacoes", self.corpo(tipo="retirada", valor="100.01")
        )

        self.assertEqual(resposta.status_code, 409)
        self.assertFalse(MovimentacaoReserva.objects.exists())

    def test_saldo_de_outra_usuaria_nao_libera_retirada(self):
        self.reserva("10.00")
        self.reserva("9000.00", usuaria=self.bia)
        self.movimentacao(APORTE, "9000.00", usuaria=self.bia)

        resposta = self.enviar(
            "post", "/api/reserva/movimentacoes", self.corpo(tipo="retirada", valor="50.00")
        )

        self.assertEqual(resposta.status_code, 409)

    def test_recusa_dados_invalidos(self):
        self.reserva("500.00")
        amanha = (HOJE + timedelta(days=1)).isoformat()
        invalidos = [
            self.corpo(tipo="transferencia"),
            self.corpo(valor=200),
            self.corpo(valor="0.00"),
            self.corpo(valor="-1.00"),
            self.corpo(valor="1.234"),
            self.corpo(data="10/10/2026"),
            self.corpo(data="2026-02-30"),
            self.corpo(data=amanha),
            self.corpo(descricao="x" * 201),
            self.corpo(descricao="Depósito\x00"),
            self.corpo(moeda="USD"),
            self.corpo(usuaria_id=self.bia.id),
        ]

        for dados in invalidos:
            with self.subTest(dados=dados):
                resposta = self.enviar("post", "/api/reserva/movimentacoes", dados)
                self.assertEqual(resposta.status_code, 422)
        self.assertFalse(MovimentacaoReserva.objects.exists())

    def test_aceita_a_data_de_hoje(self):
        self.reserva()

        resposta = self.enviar(
            "post", "/api/reserva/movimentacoes", self.corpo(data=HOJE.isoformat())
        )

        self.assertEqual(resposta.status_code, 201)

    def test_exclui_movimentacao_e_recalcula_o_saldo(self):
        self.reserva("500.00")
        retirada = self.movimentacao(RETIRADA, "100.00")

        resposta = self.client.delete(f"/api/reserva/movimentacoes/{retirada.id}")

        self.assertEqual(resposta.status_code, 204)
        self.assertEqual(self.resumo().json()["saldo_declarado"], "500.00")

    def test_nao_exclui_aporte_ja_utilizado(self):
        self.reserva("0.00")
        aporte = self.movimentacao(APORTE, "100.00")
        self.movimentacao(RETIRADA, "60.00")

        resposta = self.client.delete(f"/api/reserva/movimentacoes/{aporte.id}")

        self.assertEqual(resposta.status_code, 409)
        self.assertTrue(MovimentacaoReserva.objects.filter(id=aporte.id).exists())

    def test_exclui_aporte_que_zera_o_saldo(self):
        self.reserva("0.00")
        aporte = self.movimentacao(APORTE, "100.00")

        resposta = self.client.delete(f"/api/reserva/movimentacoes/{aporte.id}")

        self.assertEqual(resposta.status_code, 204)

    def test_lista_com_filtros_e_paginacao(self):
        antiga = self.movimentacao(APORTE, "1.00", data=date(2026, 1, 31))
        meio = self.movimentacao(RETIRADA, "1.00", data=date(2026, 2, 1))
        nova = self.movimentacao(APORTE, "1.00", data=date(2026, 3, 1))

        def ids(consulta=""):
            corpo = self.client.get(f"/api/reserva/movimentacoes{consulta}").json()
            return [item["id"] for item in corpo["itens"]]

        self.assertEqual(ids(), [nova.id, meio.id, antiga.id])
        self.assertEqual(ids("?data_inicio=2026-02-01"), [nova.id, meio.id])
        self.assertEqual(ids("?data_fim=2026-02-01"), [meio.id, antiga.id])
        self.assertEqual(ids("?tipo=retirada"), [meio.id])
        self.assertEqual(ids("?limite=1&deslocamento=1"), [meio.id])
        corpo = self.client.get("/api/reserva/movimentacoes?limite=1").json()
        self.assertEqual(corpo["quantidade"], 3)
        self.assertEqual(corpo["moeda"], "BRL")

    def test_recusa_filtros_invalidos_da_listagem(self):
        consultas = [
            "?data_inicio=2026-03-02&data_fim=2026-03-01",
            "?data_inicio=01/03/2026",
            "?tipo=transferencia",
            "?limite=0",
            "?limite=201",
            "?deslocamento=-1",
            "?categoria=1",
        ]

        for consulta in consultas:
            with self.subTest(consulta=consulta):
                resposta = self.client.get(f"/api/reserva/movimentacoes{consulta}")
                self.assertEqual(resposta.status_code, 422)

    def test_banco_recusa_valor_nao_positivo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.movimentacao(APORTE, "0.00")


class IsolamentoDaReservaTests(BaseReserva):
    def setUp(self):
        super().setUp()
        self.reserva("500.00")
        self.reserva("900.00", usuaria=self.bia)
        self.minha = self.movimentacao(APORTE, "10.00")
        self.alheia = self.movimentacao(APORTE, "777.00", usuaria=self.bia)
        self.url_alheia = f"/api/reserva/movimentacoes/{self.alheia.id}"

    def test_listagem_retorna_somente_movimentacoes_proprias(self):
        corpo = self.client.get("/api/reserva/movimentacoes").json()

        self.assertEqual([item["id"] for item in corpo["itens"]], [self.minha.id])
        self.assertEqual(corpo["quantidade"], 1)

    def test_nao_consulta_movimentacao_de_outra_usuaria_por_id(self):
        alheia = self.client.get(self.url_alheia)
        inexistente = self.client.get(f"/api/reserva/movimentacoes/{self.alheia.id + 1000}")

        self.assertEqual(alheia.status_code, 404)
        self.assertEqual(alheia.content, inexistente.content)

    def test_nao_exclui_movimentacao_de_outra_usuaria_por_id(self):
        resposta = self.client.delete(self.url_alheia)

        self.assertEqual(resposta.status_code, 404)
        self.assertTrue(MovimentacaoReserva.objects.filter(id=self.alheia.id).exists())

    def test_edicao_nao_altera_a_reserva_de_outra_usuaria(self):
        self.enviar("put", "/api/reserva", {"saldo_inicial": "1.00", "meses_cobertura": 2})

        reserva_bia = ReservaEmergencia.objects.get(usuaria=self.bia)
        self.assertEqual(reserva_bia.saldo_inicial, Decimal("900.00"))

    def test_sem_sessao_nenhuma_operacao_acessa_ou_modifica_dados(self):
        anonimo = Client()
        url = f"/api/reserva/movimentacoes/{self.minha.id}"
        corpo = {"tipo": "aporte", "valor": "1.00", "data": "2026-10-10"}

        respostas = [
            anonimo.get("/api/reserva"),
            self.enviar("put", "/api/reserva", {"saldo_inicial": "1.00"}, anonimo),
            anonimo.get("/api/reserva/movimentacoes"),
            self.enviar("post", "/api/reserva/movimentacoes", corpo, anonimo),
            anonimo.get(url),
            anonimo.delete(url),
        ]

        self.assertEqual([r.status_code for r in respostas], [401] * 6)
        self.assertEqual(MovimentacaoReserva.objects.count(), 2)

    def test_escrita_sem_token_csrf_e_recusada(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.ana)
        corpo = {"tipo": "aporte", "valor": "1.00", "data": "2026-10-10"}

        respostas = [
            self.enviar("put", "/api/reserva", {"saldo_inicial": "1.00"}, cliente),
            self.enviar("post", "/api/reserva/movimentacoes", corpo, cliente),
            cliente.delete(f"/api/reserva/movimentacoes/{self.minha.id}"),
        ]

        self.assertEqual([r.status_code for r in respostas], [403] * 3)
        self.assertEqual(MovimentacaoReserva.objects.count(), 2)

    def test_remover_usuaria_remove_sua_reserva(self):
        self.ana.delete()

        self.assertFalse(ReservaEmergencia.objects.filter(saldo_inicial=Decimal("500.00")).exists())
        self.assertFalse(MovimentacaoReserva.objects.filter(id=self.minha.id).exists())


class ContratoDaReservaTests(TestCase):
    def valores_do_tipo(self, esquema):
        esquemas = self.client.get("/api/openapi.json").json()["components"]["schemas"]
        referencia = esquemas[esquema]["properties"]["tipo"]["$ref"].rsplit("/", 1)[-1]
        return set(esquemas[referencia]["enum"])

    def test_tipos_de_movimentacao_e_de_conta_nao_se_misturam(self):
        movimentacao = {"aporte", "retirada"}
        conta = {"corrente", "poupanca", "carteira", "reserva", "outra"}

        self.assertEqual(self.valores_do_tipo("MovimentacaoIn"), movimentacao)
        self.assertEqual(self.valores_do_tipo("MovimentacaoOut"), movimentacao)
        self.assertEqual(self.valores_do_tipo("ContaIn"), conta)
        self.assertEqual(self.valores_do_tipo("ContaOut"), conta)


class RelogioRealTests(TestCase):
    def test_periodo_padrao_termina_no_mes_anterior_ao_atual(self):
        usuaria = get_user_model().objects.create_user("cris.ficticia")
        self.client.force_login(usuaria)
        atual = timezone.localdate().replace(day=1)

        corpo = self.client.get("/api/reserva").json()

        self.assertEqual(corpo["periodo"]["mes_fim"], somar_meses(atual, -1).strftime("%Y-%m"))
