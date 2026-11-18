import re
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from financas.ferramentas import (
    FERRAMENTAS,
    AcessoNegado,
    FerramentaNaoPermitida,
    ParametrosInvalidos,
    _gerar_evidencia_id,
    catalogo_ferramentas,
    executar_ferramenta,
)
from financas.models import (
    Categoria,
    ContaManual,
    MovimentacaoReserva,
    ReservaEmergencia,
    TipoLancamento,
    Transacao,
)
from financas.reserva import calcular_cobertura

HOJE = date(2026, 11, 18)
PERIODO = {"data_inicio": "2026-10-01", "data_fim": "2026-10-31"}
PARAMETROS_VALIDOS = {
    "totais_por_categoria": PERIODO,
    "resumo_periodo": PERIODO,
    "consultar_reserva": {},
    "saldos_contas": {},
}
ROTAS = {
    "/api/consultas/totais-por-categoria?data_inicio=2026-10-01&data_fim=2026-10-31",
    "/api/consultas/resumo-periodo?data_inicio=2026-10-01&data_fim=2026-10-31",
    "/api/consultas/reserva",
    "/api/consultas/saldos-contas",
}


class CoberturaTests(SimpleTestCase):
    def test_calcula_meses_cobertos_pelo_saldo(self):
        self.assertEqual(calcular_cobertura(Decimal("600.00"), Decimal("200.00")), Decimal("3.00"))

    def test_arredonda_a_metade_para_cima(self):
        self.assertEqual(calcular_cobertura(Decimal("1.00"), Decimal("8.00")), Decimal("0.13"))

    def test_sem_dados_nao_calcula_cobertura(self):
        casos = [
            (None, Decimal("200.00")),
            (Decimal("600.00"), None),
            (Decimal("600.00"), Decimal("0.00")),
        ]

        for saldo, mensais in casos:
            with self.subTest(saldo=saldo, mensais=mensais):
                self.assertIsNone(calcular_cobertura(saldo, mensais))


class BaseFerramentas(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuaria = get_user_model()
        cls.ana = Usuaria.objects.create_user("ana.ficticia")
        cls.bia = Usuaria.objects.create_user("bia.ficticia")
        cls.moradia = Categoria.objects.create(
            usuaria=cls.ana, nome="Moradia", tipo=TipoLancamento.DESPESA, essencial=True
        )
        cls.lazer = Categoria.objects.create(
            usuaria=cls.ana, nome="Lazer", tipo=TipoLancamento.DESPESA
        )
        cls.salario = Categoria.objects.create(
            usuaria=cls.ana, nome="Salário", tipo=TipoLancamento.RECEITA
        )
        cls.da_bia = Categoria.objects.create(
            usuaria=cls.bia, nome="Moradia", tipo=TipoLancamento.DESPESA, essencial=True
        )
        cls.registrar(cls.ana, cls.moradia, "1200.10", date(2026, 10, 1))
        cls.registrar(cls.ana, cls.moradia, "300.20", date(2026, 10, 31))
        cls.registrar(cls.ana, cls.lazer, "99.90", date(2026, 10, 15))
        cls.registrar(cls.ana, cls.salario, "3000.00", date(2026, 10, 5))
        cls.registrar(cls.ana, cls.moradia, "5000.00", date(2026, 9, 30))
        cls.registrar(cls.ana, cls.lazer, "5000.00", date(2026, 11, 1))
        cls.registrar(cls.bia, cls.da_bia, "777.77", date(2026, 10, 10))

    @staticmethod
    def registrar(usuaria, categoria, valor, data):
        Transacao.objects.create(
            usuaria=usuaria,
            categoria=categoria,
            tipo=categoria.tipo,
            valor=Decimal(valor),
            data=data,
        )

    def setUp(self):
        self.client.force_login(self.ana)
        relogio = mock.patch("django.utils.timezone.localdate", return_value=HOJE)
        relogio.start()
        self.addCleanup(relogio.stop)


class TotaisPorCategoriaTests(BaseFerramentas):
    def test_soma_por_categoria_no_periodo(self):
        resultado = executar_ferramenta(self.ana, "totais_por_categoria", PERIODO)
        dados = resultado["dados"]

        self.assertEqual(dados["receitas"], "3000.00")
        self.assertEqual(dados["despesas"], "1600.20")
        self.assertEqual(dados["resultado"], "1399.80")
        self.assertEqual(dados["quantidade"], 4)
        self.assertEqual(
            dados["categorias"],
            [
                {
                    "categoria_id": self.moradia.id,
                    "categoria_nome": "Moradia",
                    "tipo": "despesa",
                    "essencial": True,
                    "total": "1500.30",
                    "quantidade": 2,
                },
                {
                    "categoria_id": self.lazer.id,
                    "categoria_nome": "Lazer",
                    "tipo": "despesa",
                    "essencial": False,
                    "total": "99.90",
                    "quantidade": 1,
                },
                {
                    "categoria_id": self.salario.id,
                    "categoria_nome": "Salário",
                    "tipo": "receita",
                    "essencial": False,
                    "total": "3000.00",
                    "quantidade": 1,
                },
            ],
        )

    def test_periodo_inclui_as_duas_datas_limite(self):
        resultado = executar_ferramenta(
            self.ana,
            "totais_por_categoria",
            {"data_inicio": "2026-10-31", "data_fim": "2026-11-01"},
        )

        self.assertEqual(resultado["dados"]["despesas"], "5300.20")

    def test_filtra_por_tipo_e_categoria(self):
        por_tipo = executar_ferramenta(
            self.ana, "totais_por_categoria", {**PERIODO, "tipo": "receita"}
        )
        por_categoria = executar_ferramenta(
            self.ana, "totais_por_categoria", {**PERIODO, "categoria_id": self.lazer.id}
        )

        self.assertEqual(por_tipo["dados"]["despesas"], "0.00")
        self.assertEqual(len(por_tipo["dados"]["categorias"]), 1)
        self.assertEqual(por_categoria["dados"]["despesas"], "99.90")
        self.assertEqual(por_categoria["dados"]["quantidade"], 1)

    def test_periodo_sem_registros_retorna_totais_zerados(self):
        dados = executar_ferramenta(
            self.ana,
            "totais_por_categoria",
            {"data_inicio": "2020-01-01", "data_fim": "2020-01-31"},
        )["dados"]

        self.assertEqual(dados["receitas"], "0.00")
        self.assertEqual(dados["despesas"], "0.00")
        self.assertEqual(dados["resultado"], "0.00")
        self.assertEqual(dados["categorias"], [])

    def test_rota_devolve_o_mesmo_resultado_da_funcao(self):
        resposta = self.client.get("/api/consultas/totais-por-categoria", PERIODO)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json(), executar_ferramenta(self.ana, "totais_por_categoria", PERIODO)
        )


class ResumoEContasTests(BaseFerramentas):
    def test_resume_o_periodo(self):
        dados = executar_ferramenta(self.ana, "resumo_periodo", PERIODO)["dados"]

        self.assertEqual(
            dados,
            {
                "receitas": "3000.00",
                "despesas": "1600.20",
                "despesas_essenciais": "1500.30",
                "resultado": "1399.80",
                "quantidade": 4,
            },
        )

    def test_lista_saldos_declarados_das_contas_proprias(self):
        conta = ContaManual.objects.create(
            usuaria=self.ana, nome="Principal", tipo="corrente", saldo_declarado=Decimal("150.10")
        )
        ContaManual.objects.create(
            usuaria=self.ana, nome="Carteira", tipo="carteira", saldo_declarado=Decimal("-50.05")
        )
        ContaManual.objects.create(
            usuaria=self.bia, nome="Da Bia", tipo="corrente", saldo_declarado=Decimal("999.00")
        )

        resultado = executar_ferramenta(self.ana, "saldos_contas")
        dados = resultado["dados"]

        self.assertIsNone(resultado["periodo"])
        self.assertEqual(dados["total_declarado"], "100.05")
        self.assertEqual(dados["quantidade"], 2)
        self.assertEqual(
            dados["contas"][0],
            {"id": conta.id, "nome": "Principal", "tipo": "corrente", "saldo_declarado": "150.10"},
        )

    def test_sem_contas_retorna_total_zerado(self):
        dados = executar_ferramenta(self.bia, "saldos_contas")["dados"]

        self.assertEqual(dados, {"total_declarado": "0.00", "quantidade": 0, "contas": []})


class ReservaTests(BaseFerramentas):
    def preparar_reserva(self):
        ReservaEmergencia.objects.create(
            usuaria=self.ana, saldo_inicial=Decimal("500.00"), meses_cobertura=3
        )
        MovimentacaoReserva.objects.create(
            usuaria=self.ana,
            tipo=MovimentacaoReserva.Tipo.APORTE,
            valor=Decimal("2500.00"),
            data=date(2026, 10, 1),
        )
        MovimentacaoReserva.objects.create(
            usuaria=self.ana,
            tipo=MovimentacaoReserva.Tipo.RETIRADA,
            valor=Decimal("0.30"),
            data=date(2026, 10, 2),
        )

    def test_retorna_meta_saldo_cobertura_e_progresso(self):
        self.preparar_reserva()

        resultado = executar_ferramenta(
            self.ana, "consultar_reserva", {"mes_inicio": "2026-10", "mes_fim": "2026-10"}
        )
        dados = resultado["dados"]

        self.assertEqual(resultado["periodo"], {"inicio": "2026-10-01", "fim": "2026-10-31"})
        self.assertEqual(resultado["parametros"], {"mes_inicio": "2026-10", "mes_fim": "2026-10"})
        self.assertEqual(dados["estado"], "calculado")
        self.assertEqual(dados["despesas_essenciais_mensais"], "1500.30")
        self.assertEqual(dados["meta"], "4500.90")
        self.assertEqual(dados["saldo_declarado"], "2999.70")
        self.assertEqual(dados["meses_cobertura"], 3)
        self.assertEqual(dados["meses_cobertos"], "2.00")
        self.assertEqual(dados["progresso_percentual"], "66.65")

    def test_periodo_padrao_identifica_os_tres_ultimos_meses_completos(self):
        resultado = executar_ferramenta(self.ana, "consultar_reserva")

        self.assertEqual(resultado["periodo"], {"inicio": "2026-08-01", "fim": "2026-10-31"})

    def test_sem_dados_informa_o_que_falta_sem_inventar_cobertura(self):
        dados = executar_ferramenta(self.bia, "consultar_reserva", {
            "mes_inicio": "2026-01", "mes_fim": "2026-01",
        })["dados"]

        self.assertEqual(dados["estado"], "dados_insuficientes")
        self.assertIsNone(dados["meses_cobertos"])
        self.assertIsNone(dados["meta"])

    def test_rota_da_reserva_tambem_informa_a_cobertura(self):
        self.preparar_reserva()

        corpo = self.client.get("/api/reserva?mes_inicio=2026-10&mes_fim=2026-10").json()

        self.assertEqual(corpo["meses_cobertos"], "2.00")


class EvidenciaTests(BaseFerramentas):
    def test_resultado_identifica_ferramenta_periodo_moeda_e_origem(self):
        resultado = executar_ferramenta(self.ana, "resumo_periodo", PERIODO)

        self.assertRegex(resultado["evidencia_id"], r"^fin-[0-9a-f]{16}$")
        self.assertEqual(resultado["tipo_evidencia"], "financeira")
        self.assertEqual(resultado["ferramenta"], "resumo_periodo")
        self.assertEqual(resultado["origem"], "registros_declarados")
        self.assertEqual(resultado["moeda"], "BRL")
        self.assertEqual(resultado["periodo"], {"inicio": "2026-10-01", "fim": "2026-10-31"})
        self.assertEqual(resultado["parametros"], PERIODO)

    def test_mesma_consulta_com_os_mesmos_dados_repete_o_id(self):
        primeira = executar_ferramenta(self.ana, "resumo_periodo", PERIODO)
        segunda = executar_ferramenta(self.ana, "resumo_periodo", PERIODO)

        self.assertEqual(primeira, segunda)

    def test_id_muda_quando_os_dados_mudam(self):
        antes = executar_ferramenta(self.ana, "resumo_periodo", PERIODO)
        self.registrar(self.ana, self.lazer, "1.00", date(2026, 10, 20))

        depois = executar_ferramenta(self.ana, "resumo_periodo", PERIODO)

        self.assertNotEqual(antes["evidencia_id"], depois["evidencia_id"])

    def test_id_muda_com_o_periodo_mesmo_com_dados_iguais(self):
        janeiro = executar_ferramenta(
            self.ana, "resumo_periodo", {"data_inicio": "2020-01-01", "data_fim": "2020-01-31"}
        )
        fevereiro = executar_ferramenta(
            self.ana, "resumo_periodo", {"data_inicio": "2020-02-01", "data_fim": "2020-02-29"}
        )

        self.assertEqual(janeiro["dados"], fevereiro["dados"])
        self.assertNotEqual(janeiro["evidencia_id"], fevereiro["evidencia_id"])

    def test_id_muda_com_a_ferramenta_mesmo_com_dados_iguais(self):
        primeira = _gerar_evidencia_id("resumo_periodo", PERIODO, {"total": "1.00"})
        segunda = _gerar_evidencia_id("totais_por_categoria", PERIODO, {"total": "1.00"})

        self.assertNotEqual(primeira, segunda)


class SegurancaDasFerramentasTests(BaseFerramentas):
    def test_recusa_ferramenta_fora_da_lista(self):
        nomes = [
            "sql", "executar_sql", "raw", "query", "listar_usuarias", "excluir_transacao",
            "criar_transacao", "__class__", "", "TOTAIS_POR_CATEGORIA", None, 1, ["sql"],
        ]

        for nome in nomes:
            with self.subTest(nome=nome), self.assertRaises(FerramentaNaoPermitida):
                executar_ferramenta(self.ana, nome, {})

    def test_recusa_identidade_ou_sql_nos_parametros_de_toda_ferramenta(self):
        campos = {
            "usuaria": self.bia.id,
            "usuaria_id": self.bia.id,
            "usuario_id": self.bia.id,
            "user_id": self.bia.id,
            "sql": "SELECT * FROM auth_user",
            "query": "SELECT * FROM financas_transacao",
            "where": "1=1",
        }

        for nome, validos in PARAMETROS_VALIDOS.items():
            for campo, valor in campos.items():
                with self.subTest(ferramenta=nome, campo=campo):
                    with self.assertRaises(ParametrosInvalidos):
                        executar_ferramenta(self.ana, nome, {**validos, campo: valor})

    def test_recusa_sql_nos_campos_tipados(self):
        ataque = "2026-10-01' OR '1'='1"
        casos = [
            ("resumo_periodo", {**PERIODO, "data_inicio": ataque}),
            ("totais_por_categoria", {**PERIODO, "data_fim": "2026-10-31; DROP TABLE auth_user"}),
            ("totais_por_categoria", {**PERIODO, "categoria_id": "1 OR 1=1"}),
            ("totais_por_categoria", {**PERIODO, "categoria_id": True}),
            ("totais_por_categoria", {**PERIODO, "tipo": "despesa' OR 1=1 --"}),
            ("consultar_reserva", {"mes_inicio": "2026-10' --", "mes_fim": "2026-10"}),
        ]

        for nome, parametros in casos:
            with self.subTest(parametros=parametros), self.assertRaises(ParametrosInvalidos):
                executar_ferramenta(self.ana, nome, parametros)

    def test_recusa_periodos_invalidos(self):
        invalidos = [
            {},
            {"data_inicio": "2026-10-01"},
            {"data_fim": "2026-10-31"},
            {"data_inicio": "2026-11-01", "data_fim": "2026-10-31"},
            {"data_inicio": "2024-01-01", "data_fim": "2026-01-02"},
            {"data_inicio": "01/10/2026", "data_fim": "31/10/2026"},
        ]

        for parametros in invalidos:
            with self.subTest(parametros=parametros), self.assertRaises(ParametrosInvalidos):
                executar_ferramenta(self.ana, "resumo_periodo", parametros)

    def test_aceita_o_periodo_maximo(self):
        resultado = executar_ferramenta(
            self.ana, "resumo_periodo", {"data_inicio": "2024-01-01", "data_fim": "2026-01-01"}
        )

        self.assertEqual(resultado["ferramenta"], "resumo_periodo")

    def test_parametros_que_nao_sao_objeto_sao_recusados(self):
        for parametros in ("SELECT 1", 10, ["data_inicio"]):
            with self.subTest(parametros=parametros), self.assertRaises(ParametrosInvalidos):
                executar_ferramenta(self.ana, "resumo_periodo", parametros)

    def test_erro_nao_devolve_o_valor_recebido(self):
        segredo = "SELECT senha FROM auth_user"

        with self.assertRaises(ParametrosInvalidos) as contexto:
            executar_ferramenta(self.ana, "resumo_periodo", {**PERIODO, "sql": segredo})

        self.assertNotIn(segredo, str(contexto.exception.erros))
        self.assertNotIn(segredo, str(contexto.exception))

    def test_exige_usuaria_autenticada(self):
        for usuaria in (None, AnonymousUser(), self.bia.id, "bia.ficticia"):
            for nome, parametros in PARAMETROS_VALIDOS.items():
                with self.subTest(usuaria=usuaria, ferramenta=nome):
                    with self.assertRaises(AcessoNegado):
                        executar_ferramenta(usuaria, nome, parametros)

    def test_toda_consulta_e_leitura_filtrada_pela_usuaria(self):
        filtro = re.compile(rf'"usuaria_id" = {self.ana.id}\b')

        for nome, parametros in PARAMETROS_VALIDOS.items():
            with self.subTest(ferramenta=nome):
                with CaptureQueriesContext(connection) as consultas:
                    executar_ferramenta(self.ana, nome, parametros)

                self.assertTrue(consultas.captured_queries)
                for consulta in consultas.captured_queries:
                    self.assertTrue(consulta["sql"].startswith("SELECT"), consulta["sql"])
                    self.assertRegex(consulta["sql"], filtro)

    def test_resultados_nao_trazem_dados_de_outra_usuaria(self):
        ContaManual.objects.create(
            usuaria=self.bia, nome="Conta da Bia", tipo="corrente", saldo_declarado=Decimal("777.77")
        )
        ReservaEmergencia.objects.create(usuaria=self.bia, saldo_inicial=Decimal("777.77"))

        for nome, parametros in PARAMETROS_VALIDOS.items():
            with self.subTest(ferramenta=nome):
                resultado = executar_ferramenta(self.ana, nome, parametros)
                self.assertNotIn("777.77", str(resultado))
                self.assertNotIn("Conta da Bia", str(resultado))

    def test_categoria_de_outra_usuaria_nao_retorna_dados(self):
        dados = executar_ferramenta(
            self.ana, "totais_por_categoria", {**PERIODO, "categoria_id": self.da_bia.id}
        )["dados"]

        self.assertEqual(dados["quantidade"], 0)
        self.assertEqual(dados["categorias"], [])

    def test_catalogo_descreve_somente_as_ferramentas_permitidas(self):
        catalogo = catalogo_ferramentas()

        self.assertEqual({item["nome"] for item in catalogo}, set(FERRAMENTAS))
        for item in catalogo:
            with self.subTest(ferramenta=item["nome"]):
                propriedades = item["parametros"].get("properties", {})
                self.assertFalse({"usuaria", "usuaria_id", "sql", "query"} & set(propriedades))
                self.assertIs(item["parametros"]["additionalProperties"], False)


class RotasDeConsultaTests(BaseFerramentas):
    def test_rotas_exigem_sessao(self):
        anonimo = Client()

        for rota in ROTAS | {"/api/consultas/ferramentas"}:
            with self.subTest(rota=rota):
                self.assertEqual(anonimo.get(rota).status_code, 401)

    def test_contrato_publica_somente_leitura(self):
        caminhos = self.client.get("/api/openapi.json").json()["paths"]
        consultas = {c: m for c, m in caminhos.items() if c.startswith("/api/consultas/")}

        self.assertEqual(len(consultas), len(FERRAMENTAS) + 1)
        for caminho, metodos in consultas.items():
            with self.subTest(caminho=caminho):
                self.assertEqual(set(metodos), {"get"})

    def test_metodos_de_escrita_sao_recusados(self):
        for rota in ROTAS:
            for metodo in ("post", "put", "patch", "delete"):
                with self.subTest(rota=rota, metodo=metodo):
                    resposta = getattr(self.client, metodo)(rota)
                    self.assertEqual(resposta.status_code, 405)

    def test_catalogo_aponta_para_rotas_existentes(self):
        caminhos = self.client.get("/api/openapi.json").json()["paths"]
        catalogo = self.client.get("/api/consultas/ferramentas").json()

        self.assertEqual({item["rota"] for item in catalogo} - set(caminhos), set())
        self.assertEqual(len(catalogo), len(FERRAMENTAS))

    def test_recusa_identidade_e_filtros_desconhecidos(self):
        for rota in ROTAS:
            separador = "&" if "?" in rota else "?"
            for campo in ("usuaria_id", "user_id", "sql"):
                with self.subTest(rota=rota, campo=campo):
                    resposta = self.client.get(f"{rota}{separador}{campo}={self.bia.id}")
                    self.assertEqual(resposta.status_code, 422)

    def test_recusa_parametros_invalidos(self):
        consultas = [
            "/api/consultas/totais-por-categoria",
            "/api/consultas/totais-por-categoria?data_inicio=2026-10-01",
            "/api/consultas/resumo-periodo?data_inicio=2026-11-01&data_fim=2026-10-01",
            "/api/consultas/resumo-periodo?data_inicio=2024-01-01&data_fim=2026-01-02",
            "/api/consultas/totais-por-categoria?data_inicio=2026-10-01&data_fim=2026-10-31&tipo=x",
            "/api/consultas/reserva?mes_inicio=2026-10",
            "/api/consultas/reserva?mes_inicio=2026-11&mes_fim=2026-11",
        ]

        for consulta in consultas:
            with self.subTest(consulta=consulta):
                self.assertEqual(self.client.get(consulta).status_code, 422)

    def test_duas_usuarias_recebem_somente_os_proprios_totais(self):
        cliente_bia = Client()
        cliente_bia.force_login(self.bia)
        rota = "/api/consultas/resumo-periodo"

        da_ana = self.client.get(rota, PERIODO).json()["dados"]
        da_bia = cliente_bia.get(rota, PERIODO).json()["dados"]

        self.assertEqual(da_ana["despesas"], "1600.20")
        self.assertEqual(da_bia["despesas"], "777.77")

    def test_consulta_de_reserva_devolve_periodo_e_parametros(self):
        corpo = self.client.get("/api/consultas/reserva?mes_inicio=2026-10&mes_fim=2026-10").json()

        self.assertEqual(corpo["ferramenta"], "consultar_reserva")
        self.assertEqual(corpo["parametros"], {"mes_inicio": "2026-10", "mes_fim": "2026-10"})
        self.assertEqual(corpo["periodo"], {"inicio": "2026-10-01", "fim": "2026-10-31"})
