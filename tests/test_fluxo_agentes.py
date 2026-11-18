"""Fluxo de aprovação, abstenção e falha entre os agentes (S4-01 / #75)."""
import json
from pathlib import Path
import unittest

from finance_ai.agents import contratos as c
from finance_ai.agents.fluxo import (
    ContratoInvalido,
    Etapa,
    apos_analise,
    apos_comunicacao,
    apos_pesquisa,
    apos_validacao,
    falha_de_etapa,
    inconsistencias_comunicacao,
    ler_contrato,
    resposta_aprovada,
    resposta_segura,
)

VALIDOS = Path(__file__).resolve().parents[1] / "contracts" / "agentes" / "exemplos" / "validos"


def exemplo(nome: str):
    dados = json.loads((VALIDOS / f"{nome}.json").read_text(encoding="utf-8"))
    return c.CONTRATOS_EXPORTADOS[dados["schema"]].model_validate(dados["documento"])


class TransicoesTest(unittest.TestCase):
    def setUp(self):
        self.contexto = exemplo("ContextoAutorizado.requisicao_chat")
        self.pesquisa = exemplo("SaidaPesquisa.concluida")
        self.analise = exemplo("SaidaAnalise.analisada")
        self.aprovada = exemplo("SaidaValidacao.aprovada")
        self.reprovada = exemplo("SaidaValidacao.reprovada")
        self.comunicacao = exemplo("SaidaComunicacao.resposta_citada")

    def test_caminho_feliz(self):
        self.assertIs(apos_pesquisa(self.pesquisa).proxima, Etapa.ANALISE)
        self.assertIs(apos_pesquisa(exemplo("SaidaPesquisa.parcial")).proxima, Etapa.ANALISE)
        self.assertIs(apos_analise(self.analise).proxima, Etapa.VALIDACAO)
        self.assertIs(apos_validacao(self.aprovada, 0).proxima, Etapa.COMUNICACAO)
        self.assertIs(apos_validacao(exemplo("SaidaValidacao.aprovada_com_alertas"), 0).proxima, Etapa.COMUNICACAO)
        t = apos_comunicacao(self.pesquisa, self.analise, self.aprovada, self.comunicacao)
        self.assertIs(t.proxima, Etapa.RESPONDIDA)
        final = resposta_aprovada(self.contexto, self.comunicacao, [])
        self.assertEqual(final.estado, "respondida")
        self.assertEqual(final.fontes, self.comunicacao.fontes)

    def test_sem_evidencias_gera_abstencao(self):
        t = apos_pesquisa(exemplo("SaidaPesquisa.sem_evidencias"))
        self.assertEqual((t.proxima, t.motivo), (Etapa.ABSTENCAO, c.MotivoEncerramento.SEM_EVIDENCIAS))

    def test_pesquisa_que_falhou_gera_falha(self):
        falha = c.SaidaPesquisa(status="falha", modo="prototipo_fixtures", chamadas=[
            c.RegistroChamada(ferramenta="documentos.buscar", status="erro",
                              codigo_erro="index_not_found", duracao_ms=1)])
        self.assertEqual(apos_pesquisa(falha).motivo, c.MotivoEncerramento.FALHA_PESQUISA)

    def test_dados_insuficientes_pedem_complemento(self):
        insuf = exemplo("SaidaAnalise.dados_insuficientes")
        t = apos_analise(insuf)
        self.assertIs(t.proxima, Etapa.PEDIDO_COMPLEMENTO)
        final = resposta_segura(self.contexto, t.proxima, t.motivo, [], insuf.lacunas)
        self.assertEqual(final.estado, "pedido_complemento")
        self.assertEqual(final.perguntas_complemento, [insuf.lacunas[0].pergunta_complemento])

    def test_reprovacao_permite_uma_revisao_e_depois_abstem(self):
        primeira = apos_validacao(self.reprovada, revisoes_realizadas=0)
        self.assertIs(primeira.proxima, Etapa.ANALISE)
        self.assertEqual(primeira.feedback, list(self.reprovada.feedback))
        segunda = apos_validacao(self.reprovada, revisoes_realizadas=1)
        self.assertEqual((segunda.proxima, segunda.motivo),
                         (Etapa.ABSTENCAO, c.MotivoEncerramento.VALIDACAO_REPROVADA))

    def test_resposta_de_abstencao_nao_reaproveita_a_analise(self):
        final = resposta_segura(self.contexto, Etapa.ABSTENCAO, c.MotivoEncerramento.VALIDACAO_REPROVADA, [])
        self.assertEqual(final.fontes, [])
        for afirmacao in self.analise.afirmacoes:
            self.assertNotIn(afirmacao.texto, final.texto)
        self.assertNotIn("1.850", final.texto)

    def test_communication_nao_pode_usar_afirmacao_nao_aprovada(self):
        so_a2 = self.aprovada.model_copy(update={"afirmacoes_aprovadas": ["a2"]})
        problemas = inconsistencias_comunicacao(self.pesquisa, self.analise, so_a2, self.comunicacao)
        self.assertTrue(any("a1" in p for p in problemas))
        t = apos_comunicacao(self.pesquisa, self.analise, so_a2, self.comunicacao)
        self.assertEqual((t.proxima, t.motivo), (Etapa.FALHA, c.MotivoEncerramento.COMUNICACAO_INCONSISTENTE))

    def test_communication_nao_pode_trocar_a_evidencia_de_uma_afirmacao(self):
        doc_id = self.analise.afirmacoes[1].evidencias_ids[0]
        trocada = self.comunicacao.model_copy(update={"ligacoes": [
            c.Ligacao(afirmacao_id="a1", evidencias_ids=[doc_id])]})
        self.assertTrue(inconsistencias_comunicacao(self.pesquisa, self.analise, self.aprovada, trocada))

    def test_falhas_de_etapa(self):
        self.assertEqual(falha_de_etapa(c.Papel.ANALYSIS).motivo, c.MotivoEncerramento.FALHA_ANALISE)
        self.assertEqual(falha_de_etapa(c.Papel.RESEARCH, tempo_esgotado=True).motivo,
                         c.MotivoEncerramento.TEMPO_ESGOTADO)
        self.assertEqual(falha_de_etapa(c.Papel.COMMUNICATION, contrato=True).motivo,
                         c.MotivoEncerramento.CONTRATO_INVALIDO)
        final = resposta_segura(self.contexto, Etapa.FALHA, c.MotivoEncerramento.TEMPO_ESGOTADO, [])
        self.assertIn("Nenhum dado seu foi alterado", final.texto)

    def test_resposta_segura_nao_serve_para_resposta_aprovada(self):
        with self.assertRaises(ValueError):
            resposta_segura(self.contexto, Etapa.RESPONDIDA, c.MotivoEncerramento.SEM_EVIDENCIAS, [])

    def test_saida_de_llm_fora_do_contrato_vira_erro_tratavel(self):
        texto_gerado = '{"status": "analisada", "afirmacoes": [{"id": "a1", "texto": "Gaste menos.", ' \
                       '"natureza": "opiniao", "evidencias_ids": []}]}'
        with self.assertRaises(ContratoInvalido) as ctx:
            ler_contrato(c.SaidaAnalise, texto_gerado)
        tipos = {e["type"] for e in ctx.exception.erros}
        self.assertTrue({"literal_error", "too_short"} <= tipos)
        self.assertIsInstance(ler_contrato(c.SaidaAnalise, self.analise.model_dump_json()), c.SaidaAnalise)


if __name__ == "__main__":
    unittest.main()
