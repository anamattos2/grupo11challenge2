"""Fluxo dos agentes executado no LangGraph (S4-01 / #75).

Os quatro agentes são falsos: devolvem exemplos fictícios de
``contracts/agentes/exemplos``. O que se testa é o caminho pelo grafo.
"""
import json
from pathlib import Path
import unittest

from finance_ai.agents import contratos as c
from finance_ai.agents.fluxo import ContratoInvalido
from finance_ai.agents.grafo import Agentes, construir_grafo, diagrama_mermaid, executar_fluxo

RAIZ = Path(__file__).resolve().parents[1]
VALIDOS = RAIZ / "contracts" / "agentes" / "exemplos" / "validos"


def exemplo(nome: str):
    dados = json.loads((VALIDOS / f"{nome}.json").read_text(encoding="utf-8"))
    return c.CONTRATOS_EXPORTADOS[dados["schema"]].model_validate(dados["documento"])


class Roteiro:
    """Agente falso que devolve as respostas na ordem e guarda as entradas."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.entradas = []

    def __call__(self, entrada):
        self.entradas.append(entrada)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class GrafoTest(unittest.TestCase):
    def setUp(self):
        self.contexto = exemplo("ContextoAutorizado.requisicao_chat")
        self.pergunta = "Quanto gastei com despesas essenciais em outubro?"

    def rodar(self, research=None, analysis=None, validation=None, communication=None, **kwargs):
        self.agentes = Agentes(
            research=research or Roteiro(exemplo("SaidaPesquisa.concluida")),
            analysis=analysis or Roteiro(exemplo("SaidaAnalise.analisada")),
            validation=validation or Roteiro(exemplo("SaidaValidacao.aprovada")),
            communication=communication or Roteiro(exemplo("SaidaComunicacao.resposta_citada")),
        )
        return executar_fluxo(construir_grafo(self.agentes, **kwargs), self.contexto, self.pergunta)

    def test_caminho_feliz_chega_a_resposta_com_fontes(self):
        resposta = self.rodar()
        self.assertEqual(resposta.estado, "respondida")
        self.assertEqual(len(resposta.fontes), 2)
        self.assertEqual([e.papel.value for e in resposta.etapas],
                         ["research", "analysis", "validation", "communication"])
        # O contexto autorizado chega intacto a cada agente.
        self.assertEqual(self.agentes.research.entradas[0].contexto, self.contexto)

    def test_sem_evidencias_abstem_sem_chamar_os_outros_agentes(self):
        analysis = Roteiro()
        resposta = self.rodar(research=Roteiro(exemplo("SaidaPesquisa.sem_evidencias")), analysis=analysis)
        self.assertEqual((resposta.estado, resposta.motivo), ("abstencao", c.MotivoEncerramento.SEM_EVIDENCIAS))
        self.assertEqual(analysis.entradas, [])

    def test_dados_insuficientes_pedem_complemento(self):
        resposta = self.rodar(analysis=Roteiro(exemplo("SaidaAnalise.dados_insuficientes")))
        self.assertEqual(resposta.estado, "pedido_complemento")
        self.assertEqual(len(resposta.perguntas_complemento), 1)

    def test_reprovacao_volta_para_analise_com_feedback_e_depois_aprova(self):
        analysis = Roteiro(exemplo("SaidaAnalise.analisada"), exemplo("SaidaAnalise.analisada"))
        validation = Roteiro(exemplo("SaidaValidacao.reprovada"), exemplo("SaidaValidacao.aprovada"))
        resposta = self.rodar(analysis=analysis, validation=validation)
        self.assertEqual(resposta.estado, "respondida")
        self.assertEqual(analysis.entradas[0].feedback_validacao, [])
        self.assertEqual(analysis.entradas[1].feedback_validacao,
                         list(exemplo("SaidaValidacao.reprovada").feedback))

    def test_segunda_reprovacao_abstem_e_nunca_chega_a_communication(self):
        communication = Roteiro()
        resposta = self.rodar(
            analysis=Roteiro(exemplo("SaidaAnalise.analisada"), exemplo("SaidaAnalise.analisada")),
            validation=Roteiro(exemplo("SaidaValidacao.reprovada"), exemplo("SaidaValidacao.reprovada")),
            communication=communication)
        self.assertEqual((resposta.estado, resposta.motivo),
                         ("abstencao", c.MotivoEncerramento.VALIDACAO_REPROVADA))
        self.assertEqual(communication.entradas, [])
        self.assertNotIn("1.850", resposta.texto)

    def test_sem_revisao_quando_configurado(self):
        resposta = self.rodar(validation=Roteiro(exemplo("SaidaValidacao.reprovada")), max_revisoes=0)
        self.assertEqual(resposta.estado, "abstencao")

    def test_excecao_em_agente_vira_falha_controlada(self):
        resposta = self.rodar(analysis=Roteiro(RuntimeError("modelo fora do ar")))
        self.assertEqual((resposta.estado, resposta.motivo), ("falha", c.MotivoEncerramento.FALHA_ANALISE))
        self.assertEqual(resposta.etapas[-1].codigo, "excecao")
        self.assertNotIn("modelo fora do ar", resposta.texto)

    def test_saida_fora_do_contrato_vira_falha_de_contrato(self):
        resposta = self.rodar(analysis=Roteiro({"status": "analisada", "afirmacoes": []}))
        self.assertEqual((resposta.estado, resposta.motivo), ("falha", c.MotivoEncerramento.CONTRATO_INVALIDO))
        resposta = self.rodar(analysis=Roteiro(ContratoInvalido("SaidaAnalise", [])))
        self.assertEqual(resposta.motivo, c.MotivoEncerramento.CONTRATO_INVALIDO)

    def test_tempo_esgotado(self):
        resposta = self.rodar(research=Roteiro(TimeoutError()))
        self.assertEqual(resposta.motivo, c.MotivoEncerramento.TEMPO_ESGOTADO)

    def test_communication_inconsistente_vira_falha(self):
        aprovada_so_a2 = exemplo("SaidaValidacao.aprovada").model_copy(update={"afirmacoes_aprovadas": ["a2"]})
        resposta = self.rodar(validation=Roteiro(aprovada_so_a2))
        self.assertEqual((resposta.estado, resposta.motivo),
                         ("falha", c.MotivoEncerramento.COMUNICACAO_INCONSISTENTE))

    def test_diagrama_versionado_corresponde_ao_grafo(self):
        versionado = (RAIZ / "contracts" / "agentes" / "fluxo.mmd").read_text(encoding="utf-8")
        self.assertEqual(versionado, diagrama_mermaid().rstrip("\n") + "\n")
        for aresta in ("pesquisa -.-> abstencao", "validacao -.-> analise", "comunicacao -.-> respondida"):
            self.assertIn(aresta, versionado)
        self.assertNotIn("validacao -.-> respondida", versionado)


if __name__ == "__main__":
    unittest.main()
