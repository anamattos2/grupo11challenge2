"""Integração da Research com as ferramentas reais da BE-06 (S4-02 / #76, BE-06 / #88).

O pacote de IA não importa Django. Estes testes reproduzem respostas
**gravadas da BE-06 real** (``tests/dados/be06_respostas_gravadas.json``, geradas
por ``scripts/integracao_research_be06.py`` com PostgreSQL e dados fictícios) e
conferem que o adaptador e a fixture produzem a mesma evidência.
"""
from datetime import date
import json
from pathlib import Path
import unittest

from finance_ai.agents.backend import FonteFinanceiraBackend, traduzir
from finance_ai.agents.contratos import (
    ContextoAutorizado,
    EntradaPesquisa,
    OperacaoFinanceira,
    ParametrosFinanceiros,
    Permissao,
)
from finance_ai.agents.ferramentas import ErroFerramenta, RetrieverChroma
from finance_ai.agents.fixtures import ConsultaFinanceiraFixture, RetrieverFixture
from finance_ai.agents.research import ResearchAgent

GRAVADAS = Path(__file__).with_name("dados") / "be06_respostas_gravadas.json"
HOJE = date(2026, 11, 18)
OUTUBRO = ParametrosFinanceiros(periodo_inicio=date(2026, 10, 1), periodo_fim=date(2026, 10, 31))

#: Parâmetros aceitos por ferramenta, conforme contracts/consultas-financeiras.md (BE-06).
PARAMETROS_BE06 = {
    "totais_por_categoria": {"data_inicio", "data_fim", "tipo", "categoria_id"},
    "resumo_periodo": {"data_inicio", "data_fim"},
    "consultar_reserva": {"mes_inicio", "mes_fim"},
    "saldos_contas": set(),
}


class UsuariaDaSessao:
    def __init__(self, username):
        self.username = username
        self.is_authenticated = True


class ErroBE06(Exception):
    def __init__(self, codigo):
        super().__init__(codigo)
        self.codigo = codigo


class BE06Gravada:
    """Reproduz ``executar_ferramenta`` a partir das respostas gravadas."""

    def __init__(self):
        dados = json.loads(GRAVADAS.read_text(encoding="utf-8"))
        self.respostas = {
            (c["usuaria"], c["ferramenta"], json.dumps(c["parametros"], sort_keys=True)): c
            for c in dados["chamadas"]
        }
        self.chamadas = []

    def __call__(self, usuaria, nome, parametros):
        self.chamadas.append((usuaria.username, nome, dict(parametros)))
        gravada = self.respostas[(usuaria.username, nome, json.dumps(parametros, sort_keys=True))]
        if "erro" in gravada:
            raise ErroBE06(gravada["erro"]["codigo"])
        return gravada["resultado"]


def contexto(usuaria="usuaria-ficticia-a", permissoes=(Permissao.DOCUMENTOS_LER, Permissao.FINANCEIRO_LER)):
    return ContextoAutorizado(correlation_id="teste-backend-01", usuaria_ref=usuaria, conversa_id="conv-teste",
                              permissoes=list(permissoes), data_referencia=HOJE)


def fonte_real(be06=None):
    sessoes = {u: UsuariaDaSessao(u) for u in ("usuaria-ficticia-a", "usuaria-ficticia-b")}
    return FonteFinanceiraBackend(be06 or BE06Gravada(), resolver_usuaria=sessoes.get)


class TraducaoTest(unittest.TestCase):
    def test_cada_operacao_vira_uma_ferramenta_da_be06_com_parametros_aceitos(self):
        casos = [
            (OperacaoFinanceira.RESUMO_TRANSACOES, OUTUBRO.model_copy(update={"somente_essenciais": True}),
             "resumo_periodo"),
            (OperacaoFinanceira.RESUMO_TRANSACOES, OUTUBRO.model_copy(update={"tipo": "despesa"}),
             "totais_por_categoria"),
            (OperacaoFinanceira.LISTAR_CONTAS, ParametrosFinanceiros(), "saldos_contas"),
            (OperacaoFinanceira.SITUACAO_RESERVA, ParametrosFinanceiros(), "consultar_reserva"),
        ]
        for operacao, parametros, esperado in casos:
            with self.subTest(operacao=operacao.value, esperado=esperado):
                nome, enviados, _ = traduzir(operacao, parametros, HOJE)
                self.assertEqual(nome, esperado)
                self.assertLessEqual(set(enviados), PARAMETROS_BE06[nome])
                self.assertFalse([k for k in enviados if "usuaria" in k])

    def test_sem_periodo_usa_o_mes_corrente_e_registra(self):
        nome, enviados, avisos = traduzir(OperacaoFinanceira.RESUMO_TRANSACOES, ParametrosFinanceiros(), HOJE)
        self.assertEqual((enviados["data_inicio"], enviados["data_fim"]), ("2026-11-01", "2026-11-30"))
        self.assertEqual(avisos, ["periodo_padrao"])


class EquivalenciaComFixtureTest(unittest.TestCase):
    """Trocar a fixture pela BE-06 real não muda a evidência (só ``sintetica``)."""

    def comparar(self, usuaria, operacao, parametros):
        real = fonte_real().consultar(contexto(usuaria), operacao, parametros)
        ficticia = ConsultaFinanceiraFixture().consultar(contexto(usuaria), operacao, parametros)
        self.assertFalse(real.origem.sintetica)
        self.assertTrue(ficticia.origem.sintetica)
        for campo in ("id", "valores", "moeda"):
            self.assertEqual(getattr(real, campo), getattr(ficticia, campo), campo)
        self.assertEqual(real.origem.referencia_api, ficticia.origem.referencia_api)
        self.assertEqual((real.localizacao.periodo_inicio, real.localizacao.periodo_fim),
                         (ficticia.localizacao.periodo_inicio, ficticia.localizacao.periodo_fim))
        self.assertEqual(real.localizacao.filtros["ferramenta"], ficticia.localizacao.filtros["ferramenta"])
        self.assertTrue(real.localizacao.filtros["evidencia_backend"].startswith("fin-"))
        return real, ficticia

    def test_despesas_essenciais(self):
        real, _ = self.comparar("usuaria-ficticia-a", OperacaoFinanceira.RESUMO_TRANSACOES,
                                OUTUBRO.model_copy(update={"tipo": "despesa", "somente_essenciais": True}))
        self.assertEqual(real.valores["despesas"], "1850.40")

    def test_despesas_do_mes_por_usuaria(self):
        a, _ = self.comparar("usuaria-ficticia-a", OperacaoFinanceira.RESUMO_TRANSACOES,
                             OUTUBRO.model_copy(update={"tipo": "despesa"}))
        b, _ = self.comparar("usuaria-ficticia-b", OperacaoFinanceira.RESUMO_TRANSACOES,
                             OUTUBRO.model_copy(update={"tipo": "despesa"}))
        self.assertEqual((a.valores["despesas"], b.valores["despesas"]), ("1930.40", "999.99"))

    def test_saldos_das_contas(self):
        real, ficticia = self.comparar("usuaria-ficticia-a", OperacaoFinanceira.LISTAR_CONTAS,
                                       ParametrosFinanceiros())
        self.assertEqual(real.localizacao.registros, ficticia.localizacao.registros)
        self.assertEqual(real.resumo, ficticia.resumo)

    def test_reserva_calculada_e_reserva_sem_dados(self):
        a, fa = self.comparar("usuaria-ficticia-a", OperacaoFinanceira.SITUACAO_RESERVA, ParametrosFinanceiros())
        self.assertEqual(a.valores["meta"], "5551.20")
        self.assertEqual(a.resumo, fa.resumo)
        b, fb = self.comparar("usuaria-ficticia-b", OperacaoFinanceira.SITUACAO_RESERVA, ParametrosFinanceiros())
        self.assertIsNone(b.valores["meta"])
        self.assertEqual(b.resumo, fb.resumo)


class SegurancaTest(unittest.TestCase):
    def test_referencia_sem_sessao_nao_chega_ao_backend(self):
        be06 = BE06Gravada()
        with self.assertRaises(ErroFerramenta) as ctx:
            fonte_real(be06).consultar(contexto("ref-desconhecida"), OperacaoFinanceira.LISTAR_CONTAS,
                                       ParametrosFinanceiros())
        self.assertEqual(ctx.exception.codigo, "contexto_ausente")
        self.assertEqual(be06.chamadas, [])

    def test_erros_da_be06_viram_codigos_estaveis(self):
        for codigo_be06, esperado in (("acesso_negado", "permissao_ausente"),
                                      ("parametros_invalidos", "parametros_invalidos"),
                                      ("ferramenta_nao_permitida", "ferramenta_nao_permitida")):
            def falha(usuaria, nome, parametros, codigo=codigo_be06):
                raise ErroBE06(codigo)
            with self.subTest(codigo=codigo_be06):
                with self.assertRaises(ErroFerramenta) as ctx:
                    fonte_real(falha).consultar(contexto(), OperacaoFinanceira.LISTAR_CONTAS, ParametrosFinanceiros())
                self.assertEqual(ctx.exception.codigo, esperado)

    def test_gravacao_confirma_que_a_be06_recusa_identidade_e_sql(self):
        gravadas = json.loads(GRAVADAS.read_text(encoding="utf-8"))["chamadas"]
        recusadas = {(c["ferramenta"], json.dumps(c["parametros"])): c["erro"]["codigo"]
                     for c in gravadas if "erro" in c}
        self.assertEqual(recusadas[("saldos_contas", '{"usuaria_id": 2}')], "parametros_invalidos")
        self.assertEqual(recusadas[("executar_sql", "{}")], "ferramenta_nao_permitida")

    def test_resposta_de_outra_ferramenta_e_recusada(self):
        def troca(usuaria, nome, parametros):
            return {**BE06Gravada()(usuaria, "saldos_contas", {}), "ferramenta": "consultar_reserva"}
        with self.assertRaises(ErroFerramenta) as ctx:
            fonte_real(troca).consultar(contexto(), OperacaoFinanceira.LISTAR_CONTAS, ParametrosFinanceiros())
        self.assertEqual(ctx.exception.codigo, "resposta_invalida")


class AgenteComBackendTest(unittest.TestCase):
    def test_research_com_be06_e_fixture_documental_continua_marcada_como_prototipo(self):
        saida = ResearchAgent(RetrieverFixture(), fonte_real()).executar(EntradaPesquisa(
            contexto=contexto(), pergunta="Quanto gastei com despesas essenciais em outubro e por que devo ter "
                                          "uma reserva de emergência?"))
        self.assertEqual(saida.modo, "prototipo_fixtures")
        financeira = next(e for e in saida.evidencias if e.tipo == "financeira")
        self.assertFalse(financeira.origem.sintetica)
        self.assertEqual(financeira.valores["despesas"], "1850.40")

    def test_research_so_com_ferramentas_reais_e_integrada(self):
        sem_documentos = lambda *a, **k: {"schema_version": 1, "status": "no_results", "evidencias": [], "error": None}  # noqa: E731
        retriever = RetrieverChroma(db_path=Path("indice"), colecao="corpus", busca=sem_documentos)
        be06 = BE06Gravada()
        saida = ResearchAgent(retriever, fonte_real(be06)).executar(EntradaPesquisa(
            contexto=contexto(), pergunta="Qual o saldo das minhas contas?"))
        self.assertEqual((saida.modo, saida.status), ("integrado", "concluida"))
        self.assertEqual(be06.chamadas, [("usuaria-ficticia-a", "saldos_contas", {})])


if __name__ == "__main__":
    unittest.main()
