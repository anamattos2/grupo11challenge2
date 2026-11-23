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


def pesquisa_de_setembro() -> c.SaidaPesquisa:
    """O que a Research devolve ao atender o pedido c1 (total de setembro)."""
    fin = next(e for e in exemplo("SaidaPesquisa.concluida").evidencias if e.tipo == "financeira")
    setembro = fin.model_copy(update={"id": "fin:resumo_transacoes:aaaaaaaaaaaa"})
    return c.SaidaPesquisa(status="concluida", modo="prototipo_fixtures", evidencias=[setembro], chamadas=[
        c.RegistroChamada(ferramenta="financeiro.consultar", operacao="resumo_transacoes", pedido_id="c1",
                          status="ok", evidencias_ids=[setembro.id], duracao_ms=3)])


class GrafoTest(unittest.TestCase):
    def setUp(self):
        self.contexto = exemplo("ContextoAutorizado.requisicao_chat")
        self.pergunta = "Quanto gastei com despesas essenciais em outubro?"

    def rodar(self, research=None, analysis=None, validation=None, communication=None, **kwargs):
        self.agentes = Agentes(
            research=research or Roteiro(exemplo("SaidaPesquisa.concluida")),
            analysis=analysis or Roteiro(exemplo("SaidaAnalise.analisada")),
            validation=validation or Roteiro(exemplo("SaidaValidacao.aprovada")),
            communication=communication or Roteiro(exemplo("SaidaComunicacao.paragrafos")),
        )
        return executar_fluxo(construir_grafo(self.agentes, **kwargs), self.contexto, self.pergunta)

    def test_caminho_feliz_chega_a_resposta_com_fontes_e_ligacoes(self):
        resposta = self.rodar()
        self.assertEqual((resposta.estado, resposta.redacao), ("respondida", "communication"))
        self.assertEqual(len(resposta.fontes), 2)
        self.assertEqual(len(resposta.ligacoes), 2)
        self.assertEqual([e.papel.value for e in resposta.etapas],
                         ["research", "analysis", "validation", "communication"])
        self.assertEqual(self.agentes.research.entradas[0].contexto, self.contexto)
        self.assertEqual(self.agentes.research.entradas[0].chamadas_solicitadas, ())

    # Item 1 da revisão ------------------------------------------------------

    def test_redacao_com_afirmacao_nao_aprovada_sai_literal(self):
        so_a2 = exemplo("SaidaValidacao.aprovada").model_copy(update={"afirmacoes_aprovadas": ("a2",)})
        resposta = self.rodar(validation=Roteiro(so_a2))
        self.assertEqual((resposta.estado, resposta.redacao), ("respondida", "literal"))
        self.assertNotIn("1.850", resposta.texto)
        self.assertEqual(resposta.etapas[-1].codigo, "redacao_substituida")

    def test_falha_da_communication_nao_perde_o_conteudo_aprovado(self):
        resposta = self.rodar(communication=Roteiro(RuntimeError("modelo fora do ar")))
        self.assertEqual((resposta.estado, resposta.redacao), ("respondida", "literal"))
        self.assertIn(exemplo("SaidaAnalise.analisada").afirmacoes[0].texto, resposta.texto)
        self.assertNotIn("modelo fora do ar", resposta.texto)

    # Item 2 da revisão ------------------------------------------------------

    def test_pedido_de_calculo_volta_a_research_e_completa_a_analise(self):
        research = Roteiro(exemplo("SaidaPesquisa.concluida"), pesquisa_de_setembro())
        analysis = Roteiro(exemplo("SaidaAnalise.precisa_calculo"), exemplo("SaidaAnalise.analisada"))
        resposta = self.rodar(research=research, analysis=analysis)
        self.assertEqual(resposta.estado, "respondida")
        solicitadas = research.entradas[1].chamadas_solicitadas
        self.assertEqual([(s.operacao.value, s.pedido_id) for s in solicitadas], [("resumo_transacoes", "c1")])
        segunda = analysis.entradas[1]
        self.assertEqual(segunda.calculos_ja_pedidos, ("c1",))
        self.assertIn("fin:resumo_transacoes:aaaaaaaaaaaa", {e.id for e in segunda.pesquisa.evidencias})
        self.assertEqual(len(segunda.pesquisa.evidencias), 3)
        self.assertEqual([e.papel.value for e in resposta.etapas],
                         ["research", "analysis", "research", "analysis", "validation", "communication"])

    def test_segundo_pedido_de_calculo_abstem(self):
        research = Roteiro(exemplo("SaidaPesquisa.concluida"), pesquisa_de_setembro())
        pede = exemplo("SaidaAnalise.precisa_calculo")
        resposta = self.rodar(research=research, analysis=Roteiro(pede, pede))
        self.assertEqual((resposta.estado, resposta.motivo),
                         ("abstencao", c.MotivoEncerramento.CALCULO_INDISPONIVEL))
        self.assertEqual(len(research.entradas), 2)

    # Item 3 da revisão ------------------------------------------------------

    def test_busca_vazia_sem_permissao_e_falha_terminam_de_formas_diferentes(self):
        esperado = {
            "SaidaPesquisa.sem_evidencias": ("abstencao", c.MotivoEncerramento.SEM_EVIDENCIAS),
            "SaidaPesquisa.sem_permissao": ("abstencao", c.MotivoEncerramento.SEM_PERMISSAO),
            "SaidaPesquisa.falha": ("falha", c.MotivoEncerramento.FALHA_PESQUISA),
        }
        textos = set()
        for nome, (estado, motivo) in esperado.items():
            with self.subTest(pesquisa=nome):
                analysis = Roteiro()
                resposta = self.rodar(research=Roteiro(exemplo(nome)), analysis=analysis)
                self.assertEqual((resposta.estado, resposta.motivo), (estado, motivo))
                self.assertEqual(analysis.entradas, [])
                textos.add(resposta.texto)
        self.assertEqual(len(textos), 3)

    # Item 4 da revisão ------------------------------------------------------

    def test_agente_nao_consegue_alterar_o_que_recebeu_nem_o_estado(self):
        pesquisa = exemplo("SaidaPesquisa.concluida")
        tentativas = []

        def analysis_intrometida(entrada):
            fin = next(e for e in entrada.pesquisa.evidencias if e.tipo == "financeira")
            for nome, acao in (
                ("lista", lambda: entrada.pesquisa.evidencias.append(fin)),
                ("mapa", lambda: fin.valores.__setitem__("despesas", "0.00")),
                ("atributo", lambda: setattr(entrada.pesquisa, "status", "falha")),
            ):
                try:
                    acao()
                    tentativas.append((nome, "alterou"))
                except (AttributeError, TypeError, ValueError):
                    tentativas.append((nome, "bloqueado"))
            self.assertIsNot(entrada.pesquisa, pesquisa)
            return exemplo("SaidaAnalise.analisada")

        validation = Roteiro(exemplo("SaidaValidacao.aprovada"))
        resposta = self.rodar(research=Roteiro(pesquisa), analysis=analysis_intrometida, validation=validation)
        self.assertEqual(tentativas, [("lista", "bloqueado"), ("mapa", "bloqueado"), ("atributo", "bloqueado")])
        self.assertEqual(resposta.estado, "respondida")
        recebida = validation.entradas[0].pesquisa
        self.assertEqual(recebida, pesquisa)
        self.assertIsNot(recebida, pesquisa)

    # Revisão 2 do #135 ------------------------------------------------------

    def test_validation_aprovando_id_inexistente_vira_falha_e_nao_excecao(self):
        fantasma = exemplo("SaidaValidacao.aprovada").model_copy(update={"afirmacoes_aprovadas": ("a1", "a9")})
        communication = Roteiro()
        resposta = self.rodar(validation=Roteiro(fantasma), communication=communication)
        self.assertEqual((resposta.estado, resposta.motivo), ("falha", c.MotivoEncerramento.CONTRATO_INVALIDO))
        self.assertEqual(resposta.etapas[-1].codigo, "referencia_inexistente")
        self.assertEqual(communication.entradas, [])

    def test_analysis_citando_evidencia_inexistente_vira_falha_e_nao_chega_a_validation(self):
        analise = exemplo("SaidaAnalise.analisada")
        a1 = analise.afirmacoes[0].model_copy(update={"evidencias_ids": ("doc:" + "f" * 16,)})
        validation = Roteiro()
        resposta = self.rodar(analysis=Roteiro(analise.model_copy(update={"afirmacoes": (a1,)})),
                              validation=validation)
        self.assertEqual((resposta.estado, resposta.motivo), ("falha", c.MotivoEncerramento.CONTRATO_INVALIDO))
        self.assertEqual(validation.entradas, [])

    def test_feedback_da_reprovacao_sobrevive_a_um_pedido_de_calculo(self):
        reprovada = exemplo("SaidaValidacao.reprovada")
        analysis = Roteiro(exemplo("SaidaAnalise.analisada"), exemplo("SaidaAnalise.precisa_calculo"),
                           exemplo("SaidaAnalise.analisada"))
        resposta = self.rodar(
            research=Roteiro(exemplo("SaidaPesquisa.concluida"), pesquisa_de_setembro()),
            analysis=analysis,
            validation=Roteiro(reprovada, exemplo("SaidaValidacao.aprovada")))
        self.assertEqual(resposta.estado, "respondida")
        self.assertEqual([e.feedback_validacao for e in analysis.entradas],
                         [(), reprovada.feedback, reprovada.feedback])

    def test_erro_dentro_do_orquestrador_nunca_escapa(self):
        from unittest import mock
        with mock.patch("finance_ai.agents.grafo.montar_resposta", side_effect=KeyError("a9")):
            resposta = self.rodar()
        self.assertEqual((resposta.estado, resposta.motivo), ("falha", c.MotivoEncerramento.CONTRATO_INVALIDO))
        with mock.patch("finance_ai.agents.grafo.apos_pesquisa", side_effect=RuntimeError("bug")):
            resposta = self.rodar()
        self.assertEqual((resposta.estado, resposta.motivo), ("falha", c.MotivoEncerramento.ERRO_INTERNO))
        self.assertNotIn("bug", resposta.texto)

    # Demais caminhos ---------------------------------------------------------

    def test_dados_insuficientes_pedem_complemento(self):
        resposta = self.rodar(analysis=Roteiro(exemplo("SaidaAnalise.dados_insuficientes")))
        self.assertEqual(resposta.estado, "pedido_complemento")
        self.assertEqual(len(resposta.perguntas_complemento), 1)

    def test_reprovacao_volta_para_analise_com_feedback_e_depois_aprova(self):
        analysis = Roteiro(exemplo("SaidaAnalise.analisada"), exemplo("SaidaAnalise.analisada"))
        validation = Roteiro(exemplo("SaidaValidacao.reprovada"), exemplo("SaidaValidacao.aprovada"))
        resposta = self.rodar(analysis=analysis, validation=validation)
        self.assertEqual(resposta.estado, "respondida")
        self.assertEqual(analysis.entradas[0].feedback_validacao, ())
        self.assertEqual(analysis.entradas[1].feedback_validacao, exemplo("SaidaValidacao.reprovada").feedback)

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

    def test_diagrama_versionado_corresponde_ao_grafo(self):
        versionado = (RAIZ / "contracts" / "agentes" / "fluxo.mmd").read_text(encoding="utf-8")
        self.assertEqual(versionado, diagrama_mermaid().rstrip("\n") + "\n")
        for aresta in ("pesquisa -.-> abstencao", "validacao -.-> analise", "analise -.-> pesquisa",
                       "comunicacao -.-> respondida"):
            self.assertIn(aresta, versionado)
        self.assertNotIn("validacao -.-> respondida", versionado)
        self.assertNotIn("comunicacao -.-> falha", versionado)


if __name__ == "__main__":
    unittest.main()
