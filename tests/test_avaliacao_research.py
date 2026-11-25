"""Avaliação offline do Research Agent (S4-02 / #76). Dados fictícios."""
from datetime import date
import json
from pathlib import Path
import unittest

from finance_ai.agents.avaliacao import avaliar, avaliar_caso, donos_dos_registros
from finance_ai.agents.contratos import ChamadaFerramenta, OperacaoFinanceira, ParametrosFinanceiros
from finance_ai.agents.fixtures import ConsultaFinanceiraFixture, RetrieverFixture
from finance_ai.agents.planejador import Plano
from finance_ai.agents.research import ResearchAgent

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "evaluations" / "research-agent" / "casos.json"
BASELINE = RAIZ / "evaluations" / "research-agent" / "baseline-regras.json"


class Oraculo:
    """Planejador que devolve exatamente o plano esperado de cada caso."""

    def __init__(self):
        self.planos = {c["pergunta"]: c["esperado"] for c in json.loads(CASOS.read_text(encoding="utf-8"))["casos"]}

    def planejar(self, pergunta, data_referencia):
        esperado = self.planos[pergunta]
        chamadas = []
        for operacao in esperado.get("operacoes") or []:
            periodo = esperado.get("periodo") if operacao == "resumo_transacoes" else None
            chamadas.append(ChamadaFerramenta(
                ferramenta="financeiro.consultar", operacao=OperacaoFinanceira(operacao),
                parametros=ParametrosFinanceiros(
                    periodo_inicio=date.fromisoformat(periodo[0]) if periodo else None,
                    periodo_fim=date.fromisoformat(periodo[1]) if periodo else None)))
        if esperado.get("documentos"):
            chamadas.append(ChamadaFerramenta(ferramenta="documentos.buscar", consulta=pergunta))
        return Plano(chamadas=chamadas)


class AvaliacaoTest(unittest.TestCase):
    def test_regras_reproduzem_a_baseline_versionada(self):
        resumo = avaliar(CASOS, lambda r, f: None, "regras").resumo()
        resumo.pop("latencia_media_ms")
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        baseline.pop("casos_versao")
        self.assertEqual(resumo, baseline,
                         "o comportamento mudou: rode scripts/avaliar_research.py --gravar-baseline e explique no PR")

    def test_nenhum_caso_viola_isolamento(self):
        relatorio = avaliar(CASOS, lambda r, f: None, "regras")
        self.assertEqual(relatorio.violacoes_isolamento, 0)
        self.assertEqual([r.id for r in relatorio.por_caso if r.violacoes_isolamento], [])

    def test_planejador_perfeito_pontua_cem_por_cento(self):
        # Confere as próprias métricas: um plano igual ao gabarito tem nota máxima.
        relatorio = avaliar(CASOS, lambda r, f: Oraculo(), "oraculo")
        for metrica in ("selecao_exata", "precisao", "revocacao", "periodo_correto", "status_correto"):
            self.assertEqual(getattr(relatorio, metrica), 1.0, metrica)

    def test_plano_recusado_pelo_contrato_e_desfecho_seguro(self):
        class Malicioso:
            def planejar(self, pergunta, data_referencia):
                return Plano(chamadas=[{"ferramenta": "financeiro.consultar", "operacao": "resumo_transacoes",
                                        "parametros": {"usuaria_id": "usuaria-ficticia-b"}}])

        agente = ResearchAgent(RetrieverFixture(), ConsultaFinanceiraFixture(), Malicioso())
        casos = {c["id"]: c for c in json.loads(CASOS.read_text(encoding="utf-8"))["casos"]}
        seguranca = avaliar_caso(agente, casos["injecao_outra_usuaria"], date(2026, 11, 18), donos_dos_registros())
        self.assertTrue(seguranca.plano_bloqueado)
        self.assertIsNone(seguranca.selecao_exata)
        pessoal = avaliar_caso(agente, casos["gastos_outubro"], date(2026, 11, 18), donos_dos_registros())
        self.assertIs(pessoal.selecao_exata, False)

    def test_donos_cobrem_transacoes_e_contas_sem_sobreposicao(self):
        donos = donos_dos_registros()
        self.assertEqual(donos["usuaria-ficticia-b"], {"11", "201", "202"})
        self.assertFalse(donos["usuaria-ficticia-a"] & donos["usuaria-ficticia-b"])


if __name__ == "__main__":
    unittest.main()
