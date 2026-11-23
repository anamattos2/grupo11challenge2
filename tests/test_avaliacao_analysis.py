"""Avaliação offline do Analysis Agent (S4-03 / #77): baseline e redator adversário."""
import json
from pathlib import Path
import unittest

from langchain_core.runnables import RunnableLambda

from finance_ai.agents.analysis import RascunhoLLM, RascunhosLLM, RedatorLLM
from finance_ai.agents.avaliacao_analysis import avaliar
from finance_ai.agents.redacao import MARCADOR

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "evaluations" / "analysis-agent" / "casos.json"
BASELINE = RAIZ / "evaluations" / "analysis-agent" / "baseline-regras.json"


class ModeloQueInventaNumeros:
    def with_structured_output(self, schema):
        def responder(mensagens):
            marcador = MARCADOR.search(mensagens[-1].content)
            ids = [marcador.group(1)] if marcador else []
            return RascunhosLLM(afirmacoes=[RascunhoLLM(natureza="calculo", texto="Você economizou R$ 321,00.",
                                                        evidencias_ids=ids)])
        return RunnableLambda(responder)


class AvaliacaoAnalysisTest(unittest.TestCase):
    def test_regras_reproduzem_a_baseline(self):
        resumo = avaliar(CASOS).resumo()
        resumo.pop("latencia_media_ms")
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        baseline.pop("casos_versao")
        self.assertEqual(resumo, baseline)

    def test_redator_que_inventa_numeros_nunca_passa_numero_sem_origem(self):
        resumo = avaliar(CASOS, RedatorLLM(ModeloQueInventaNumeros()), "adversario").resumo()
        self.assertEqual(resumo["numeros_sem_origem"], 0)
        self.assertEqual(resumo["afirmacoes_rastreaveis"], 1.0)
        self.assertGreater(resumo["rascunhos_recusados"], 0)
        self.assertEqual(resumo["status_correto"], 1.0)


if __name__ == "__main__":
    unittest.main()
