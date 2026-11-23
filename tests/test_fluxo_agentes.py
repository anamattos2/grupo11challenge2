"""Fluxo de aprovação, abstenção e falha entre os agentes (S4-01 / #75).

Funções puras de ``fluxo.py``, sem LangGraph. Dados fictícios.
"""
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from finance_ai.agents import contratos as c
from finance_ai.agents.fluxo import (
    ContratoInvalido,
    Etapa,
    apos_analise,
    apos_pesquisa,
    apos_validacao,
    falha_de_etapa,
    inconsistencias_comunicacao,
    ler_contrato,
    mesclar_pesquisas,
    montar_resposta,
    numeros,
    resposta_segura,
)

VALIDOS = Path(__file__).resolve().parents[1] / "contracts" / "agentes" / "exemplos" / "validos"


def exemplo(nome: str):
    dados = json.loads((VALIDOS / f"{nome}.json").read_text(encoding="utf-8"))
    return c.CONTRATOS_EXPORTADOS[dados["schema"]].model_validate(dados["documento"])


def chamada(status, **extra):
    base = {"ferramenta": "documentos.buscar", "status": status, "duracao_ms": 1}
    if status in ("erro", "negada"):
        base["codigo_erro"] = "permissao_ausente" if status == "negada" else "index_not_found"
    return c.RegistroChamada(**base, **extra)


class PesquisaTest(unittest.TestCase):
    """Revisão #135, item 3: busca vazia, falta de permissão e falha são distintas."""

    def test_status_e_derivado_das_chamadas(self):
        casos = [
            (True, ["ok"], "concluida"),
            (True, ["ok", "sem_resultados"], "concluida"),
            (True, ["ok", "negada"], "parcial"),
            (True, ["ok", "erro"], "parcial"),
            (False, ["sem_resultados"], "sem_evidencias"),
            (False, ["sem_resultados", "negada"], "sem_evidencias"),
            (False, ["negada"], "sem_permissao"),
            (False, ["negada", "negada"], "sem_permissao"),
            (False, ["erro"], "falha"),
            (False, ["erro", "negada"], "falha"),
            (False, ["erro", "sem_resultados"], "falha"),
        ]
        for tem_evidencias, situacoes, esperado in casos:
            with self.subTest(situacoes=situacoes, evidencias=tem_evidencias):
                registros = [c.RegistroChamada(ferramenta="documentos.buscar", status=s, duracao_ms=0,
                                               evidencias_ids=("doc:" + "a" * 16,) if s == "ok" else (),
                                               codigo_erro={"erro": "falhou", "negada": "negada"}.get(s))
                             for s in situacoes]
                self.assertEqual(c.status_da_pesquisa(tem_evidencias, registros), esperado)

    def test_todas_as_chamadas_com_erro_nao_podem_virar_busca_vazia(self):
        with self.assertRaises(ValidationError) as ctx:
            c.SaidaPesquisa(status="sem_evidencias", modo="prototipo_fixtures", chamadas=[chamada("erro")])
        self.assertIn("o correto é 'falha'", str(ctx.exception))

    def test_todas_negadas_nao_podem_virar_busca_vazia(self):
        with self.assertRaises(ValidationError) as ctx:
            c.SaidaPesquisa(status="sem_evidencias", modo="prototipo_fixtures",
                            chamadas=[chamada("negada"), chamada("negada")])
        self.assertIn("o correto é 'sem_permissao'", str(ctx.exception))

    def test_cada_cenario_tem_destino_e_mensagem_proprios(self):
        contexto = exemplo("ContextoAutorizado.requisicao_chat")
        destinos = {}
        for nome in ("SaidaPesquisa.sem_evidencias", "SaidaPesquisa.sem_permissao", "SaidaPesquisa.falha"):
            t = apos_pesquisa(exemplo(nome))
            destinos[nome] = (t.proxima, t.motivo, resposta_segura(contexto, t.proxima, t.motivo, ()).texto)
        self.assertEqual(destinos["SaidaPesquisa.sem_evidencias"][:2],
                         (Etapa.ABSTENCAO, c.MotivoEncerramento.SEM_EVIDENCIAS))
        self.assertEqual(destinos["SaidaPesquisa.sem_permissao"][:2],
                         (Etapa.ABSTENCAO, c.MotivoEncerramento.SEM_PERMISSAO))
        self.assertEqual(destinos["SaidaPesquisa.falha"][:2], (Etapa.FALHA, c.MotivoEncerramento.FALHA_PESQUISA))
        self.assertEqual(len({texto for *_, texto in destinos.values()}), 3)
        self.assertNotIn("Não encontrei", destinos["SaidaPesquisa.falha"][2])

    def test_pesquisa_com_evidencia_segue_para_analise(self):
        self.assertIs(apos_pesquisa(exemplo("SaidaPesquisa.concluida")).proxima, Etapa.ANALISE)
        self.assertIs(apos_pesquisa(exemplo("SaidaPesquisa.parcial")).proxima, Etapa.ANALISE)


class PedidoDeCalculoTest(unittest.TestCase):
    """Revisão #135, item 2: a Analysis pede cálculo tipado e o fluxo volta à Research."""

    def setUp(self):
        self.pede = exemplo("SaidaAnalise.precisa_calculo")

    def test_primeiro_pedido_volta_a_research_com_os_calculos(self):
        t = apos_analise(self.pede, rodadas_calculo=0)
        self.assertIs(t.proxima, Etapa.PESQUISA)
        self.assertEqual([p.id for p in t.calculos], ["c1"])
        chamada_calc = t.calculos[0].como_chamada()
        self.assertEqual((chamada_calc.ferramenta, chamada_calc.pedido_id), ("financeiro.consultar", "c1"))

    def test_limite_de_rodadas_ou_pedido_repetido_abstem(self):
        for kwargs in ({"rodadas_calculo": 1}, {"rodadas_calculo": 0, "ja_pedidos": ("c1",)}):
            with self.subTest(**kwargs):
                t = apos_analise(self.pede, **kwargs)
                self.assertEqual((t.proxima, t.motivo), (Etapa.ABSTENCAO, c.MotivoEncerramento.CALCULO_INDISPONIVEL))

    def test_research_so_executa_calculos_com_pedido(self):
        exemplo("EntradaPesquisa.calculo_solicitado")  # válido
        with self.assertRaises(ValidationError):
            c.EntradaPesquisa(contexto=exemplo("ContextoAutorizado.requisicao_chat"), pergunta="x",
                              chamadas_solicitadas=[c.ChamadaFerramenta(ferramenta="documentos.buscar", consulta="x")])

    def test_mescla_soma_evidencias_e_recalcula_status(self):
        base = exemplo("SaidaPesquisa.concluida")
        fin = next(e for e in base.evidencias if e.tipo == "financeira")
        setembro = fin.model_copy(update={"id": "fin:resumo_transacoes:aaaaaaaaaaaa"})
        complemento = c.SaidaPesquisa(status="concluida", modo="prototipo_fixtures", evidencias=[setembro],
                                      chamadas=[c.RegistroChamada(ferramenta="financeiro.consultar",
                                                                  operacao="resumo_transacoes", pedido_id="c1",
                                                                  status="ok", evidencias_ids=[setembro.id],
                                                                  duracao_ms=2)])
        mesclada = mesclar_pesquisas(base, complemento)
        self.assertEqual(len(mesclada.evidencias), len(base.evidencias) + 1)
        self.assertEqual(mesclada.status, "concluida")
        self.assertEqual(mesclada.chamadas[-1].pedido_id, "c1")

        falhou = c.SaidaPesquisa(status="falha", modo="prototipo_fixtures", chamadas=[
            c.RegistroChamada(ferramenta="financeiro.consultar", operacao="resumo_transacoes", pedido_id="c1",
                              status="erro", codigo_erro="banco_indisponivel", duracao_ms=1)])
        self.assertEqual(mesclar_pesquisas(base, falhou).status, "parcial")


class ValidacaoTest(unittest.TestCase):
    def test_reprovacao_permite_uma_revisao_e_depois_abstem(self):
        reprovada = exemplo("SaidaValidacao.reprovada")
        primeira = apos_validacao(reprovada, revisoes_realizadas=0)
        self.assertEqual((primeira.proxima, primeira.feedback), (Etapa.ANALISE, reprovada.feedback))
        segunda = apos_validacao(reprovada, revisoes_realizadas=1)
        self.assertEqual((segunda.proxima, segunda.motivo),
                         (Etapa.ABSTENCAO, c.MotivoEncerramento.VALIDACAO_REPROVADA))

    def test_aprovacao_segue_para_communication(self):
        self.assertIs(apos_validacao(exemplo("SaidaValidacao.aprovada"), 0).proxima, Etapa.COMUNICACAO)
        self.assertIs(apos_validacao(exemplo("SaidaValidacao.aprovada_com_alertas"), 0).proxima,
                      Etapa.COMUNICACAO)

    def test_dados_insuficientes_pedem_complemento(self):
        insuf = exemplo("SaidaAnalise.dados_insuficientes")
        t = apos_analise(insuf)
        final = resposta_segura(exemplo("ContextoAutorizado.requisicao_chat"), t.proxima, t.motivo, (), insuf.lacunas)
        self.assertEqual(final.estado, "pedido_complemento")
        self.assertEqual(final.perguntas_complemento, (insuf.lacunas[0].pergunta_complemento,))


class RespostaFinalTest(unittest.TestCase):
    """Revisão #135, item 1: o texto final só expressa afirmações aprovadas."""

    def setUp(self):
        self.contexto = exemplo("ContextoAutorizado.requisicao_chat")
        self.pesquisa = exemplo("SaidaPesquisa.concluida")
        self.analise = exemplo("SaidaAnalise.analisada")
        self.aprovada = exemplo("SaidaValidacao.aprovada")
        self.comunicacao = exemplo("SaidaComunicacao.paragrafos")

    def montar(self, comunicacao=None, validacao=None):
        return montar_resposta(self.contexto, self.pesquisa, self.analise, validacao or self.aprovada,
                               comunicacao if comunicacao is not None else self.comunicacao, ())

    def redigir(self, *paragrafos):
        return c.SaidaComunicacao(paragrafos=[c.Paragrafo(afirmacoes_ids=ids, texto=t) for ids, t in paragrafos])

    def test_numeros_em_forma_canonica(self):
        self.assertEqual(numeros("R$ 1.850,40 em 2026"), {"1850.4", "2026"})
        self.assertEqual(numeros("1850.40"), {"1850.4"})
        self.assertEqual(numeros("meta de 6.000 e 10%"), {"6000", "10"})

    def test_redacao_conferida_vira_texto_com_citacoes_fontes_e_ligacoes(self):
        resposta, problemas = self.montar()
        self.assertEqual(problemas, [])
        self.assertEqual(resposta.redacao, "communication")
        self.assertIn("R$ 1.850,40", resposta.texto)
        self.assertTrue(resposta.texto.split("\n\n")[0].endswith("[1]"))
        self.assertEqual([f.rotulo[:3] for f in resposta.fontes], ["[1]", "[2]"])
        # Ligações vêm da Analysis, não da Communication.
        self.assertEqual({l.afirmacao_id: l.evidencias_ids for l in resposta.ligacoes},
                         {a.id: a.evidencias_ids for a in self.analise.afirmacoes})

    def test_paragrafo_com_afirmacao_nao_aprovada_e_substituido_pelo_texto_literal(self):
        so_a2 = self.aprovada.model_copy(update={"afirmacoes_aprovadas": ("a2",)})
        problemas = inconsistencias_comunicacao(self.analise, so_a2, self.comunicacao)
        self.assertTrue(any("a1" in p and "não foi aprovada" in p for p in problemas))
        resposta, _ = self.montar(validacao=so_a2)
        self.assertEqual(resposta.redacao, "literal")
        self.assertNotIn("1.850", resposta.texto)
        self.assertEqual([l.afirmacao_id for l in resposta.ligacoes], ["a2"])

    def test_numero_que_nao_esta_nas_afirmacoes_e_barrado(self):
        inventada = self.redigir((("a1",), "Você gastou R$ 1.950,40 em outubro de 2026."),
                                 (("a2",), self.comunicacao.paragrafos[1].texto))
        problemas = inconsistencias_comunicacao(self.analise, self.aprovada, inventada)
        self.assertTrue(any("1950.4" in p for p in problemas))
        resposta, _ = self.montar(inventada)
        self.assertEqual(resposta.redacao, "literal")
        self.assertNotIn("1.950", resposta.texto)
        self.assertIn(self.analise.afirmacoes[0].texto, resposta.texto)

    def test_numero_reformatado_e_aceito_mas_citacao_manual_nao(self):
        reformatado = self.redigir((("a1",), "Em outubro de 2026 foram 1850.40 reais em despesas essenciais."),
                                   (("a2",), self.comunicacao.paragrafos[1].texto))
        self.assertEqual(inconsistencias_comunicacao(self.analise, self.aprovada, reformatado), [])
        com_marca = self.redigir((("a1",), self.comunicacao.paragrafos[0].texto + " [7]"),
                                 (("a2",), self.comunicacao.paragrafos[1].texto))
        self.assertTrue(inconsistencias_comunicacao(self.analise, self.aprovada, com_marca))

    def test_afirmacao_aprovada_omitida_e_barrada(self):
        so_a2 = self.redigir((("a2",), self.comunicacao.paragrafos[1].texto))
        self.assertIn("afirmações aprovadas fora do texto: ['a1']",
                      inconsistencias_comunicacao(self.analise, self.aprovada, so_a2))

    def test_sem_communication_a_resposta_sai_literal(self):
        resposta, problemas = self.montar(comunicacao=False)
        self.assertEqual(resposta.redacao, "literal")
        self.assertTrue(problemas)

    def test_exemplo_literal_versionado_corresponde_a_regra(self):
        literal = exemplo("RespostaFinal.respondida_literal")
        self.assertEqual(literal.redacao, "literal")
        self.assertNotIn("1.950", literal.texto)


class ContratosNaFronteiraTest(unittest.TestCase):
    def test_saida_de_llm_fora_do_contrato_vira_erro_tratavel(self):
        texto_gerado = '{"status": "analisada", "afirmacoes": [{"id": "a1", "texto": "Gaste menos.", ' \
                       '"natureza": "opiniao", "evidencias_ids": []}]}'
        with self.assertRaises(ContratoInvalido) as ctx:
            ler_contrato(c.SaidaAnalise, texto_gerado)
        self.assertTrue({"literal_error", "too_short"} <= {e["type"] for e in ctx.exception.erros})

    def test_ler_contrato_devolve_copia_independente(self):
        original = exemplo("SaidaAnalise.analisada")
        lido = ler_contrato(c.SaidaAnalise, original)
        self.assertEqual(lido, original)
        self.assertIsNot(lido, original)
        self.assertIsNot(lido.afirmacoes[0], original.afirmacoes[0])

    def test_falhas_de_etapa(self):
        self.assertEqual(falha_de_etapa(c.Papel.ANALYSIS).motivo, c.MotivoEncerramento.FALHA_ANALISE)
        self.assertEqual(falha_de_etapa(c.Papel.RESEARCH, tempo_esgotado=True).motivo,
                         c.MotivoEncerramento.TEMPO_ESGOTADO)
        self.assertEqual(falha_de_etapa(c.Papel.COMMUNICATION, contrato=True).motivo,
                         c.MotivoEncerramento.CONTRATO_INVALIDO)

    def test_resposta_segura_nao_serve_para_resposta_aprovada(self):
        with self.assertRaises(ValueError):
            resposta_segura(exemplo("ContextoAutorizado.requisicao_chat"), Etapa.RESPONDIDA,
                            c.MotivoEncerramento.SEM_EVIDENCIAS, ())


if __name__ == "__main__":
    unittest.main()
