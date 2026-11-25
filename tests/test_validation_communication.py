"""Validation Agent (S4-04 / #78) e Communication Agent (S4-05 / #79).

Dados fictícios, a partir dos exemplos de ``contracts/agentes/exemplos``.
"""
import json
from pathlib import Path
import unittest

from finance_ai.agents import contratos as c
from finance_ai.agents.communication import (
    LIMITE_ALERTA,
    LIMITE_EDUCATIVO,
    LIMITE_PARCIAL,
    LIMITE_SINTETICO,
    LIMITE_SUPORTE,
    CommunicationAgent,
    prompt_redacao,
)
from finance_ai.agents.fluxo import LIMITE_PADRAO, MENSAGENS_SEGURAS, inconsistencias_comunicacao
from finance_ai.agents.grafo import Agentes, construir_grafo, executar_fluxo
from finance_ai.agents.validation import ValidationAgent, validar

VALIDOS = Path(__file__).resolve().parents[1] / "contracts" / "agentes" / "exemplos" / "validos"

TEXTO_A1 = "Em outubro de 2026 você registrou R$ 1.850,40 em despesas de categorias essenciais."
FIN = "fin:resumo_transacoes:53dd2d27e384"
DOC = "doc:4ca5959e85ae1899"


def exemplo(nome: str):
    dados = json.loads((VALIDOS / f"{nome}.json").read_text(encoding="utf-8"))
    return c.CONTRATOS_EXPORTADOS[dados["schema"]].model_validate(dados["documento"])


def afirmacao(aid, texto, natureza, *evidencias):
    return c.Afirmacao(id=aid, texto=texto, natureza=natureza, evidencias_ids=evidencias or (FIN,))


def analise(*afirmacoes):
    return c.SaidaAnalise(status="analisada", afirmacoes=afirmacoes)


def pesquisa_real() -> c.SaidaPesquisa:
    """A pesquisa do exemplo, como se viesse do acervo real e da BE-06 (sem fixture)."""
    dados = exemplo("SaidaPesquisa.concluida").model_dump(mode="json")
    dados["modo"] = "integrado"
    for evidencia in dados["evidencias"]:
        evidencia["origem"]["sintetica"] = False
    return c.SaidaPesquisa.model_validate(dados)


class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.base = exemplo("EntradaValidacao.apos_analise")

    def validar(self, analise_=None, pesquisa=None, contexto=None):
        entrada = self.base.model_copy(update={k: v for k, v in {
            "analise": analise_, "pesquisa": pesquisa, "contexto": contexto}.items() if v is not None})
        return validar(c.EntradaValidacao.model_validate(entrada.model_dump()))

    def regras(self, saida, resultado):
        return {(v.regra.value, v.afirmacao_id) for v in saida.verificacoes if v.resultado == resultado}

    def test_exemplo_aprovado_com_alerta_de_fonte_sintetica(self):
        saida = ValidationAgent()(self.base)
        self.assertEqual(saida.decisao, "aprovada_com_alertas")
        self.assertEqual(saida.afirmacoes_aprovadas, ("a1", "a2"))
        self.assertEqual(self.regras(saida, "alerta"),
                         {("referencias_existentes", "a1"), ("referencias_existentes", "a2")})
        self.assertIn(("suporte_documental", "a2"), self.regras(saida, "ok"))
        self.assertIn(("numeros_conferem", "a1"), self.regras(saida, "ok"))

    def test_fontes_reais_e_suporte_completo_aprovam_sem_alerta(self):
        saida = self.validar(pesquisa=pesquisa_real())
        self.assertEqual(saida.decisao, "aprovada")
        self.assertFalse(self.regras(saida, "alerta"))

    def test_referencia_inexistente_reprova(self):
        saida = self.validar(analise(afirmacao("a1", TEXTO_A1, "dado_pessoal", "fin:resumo_transacoes:ffffffffffff")))
        self.assertEqual((saida.decisao, saida.motivo_bloqueio), ("reprovada", c.MotivoBloqueio.REFERENCIA_INEXISTENTE))
        self.assertEqual(saida.alegacoes_sem_suporte, ("a1",))
        self.assertIn("ffffffffffff", saida.feedback[0])

    def test_numero_divergente_reprova_com_feedback(self):
        texto = TEXTO_A1.replace("1.850,40", "1.900,00")
        saida = self.validar(analise(afirmacao("a1", texto, "dado_pessoal")))
        self.assertEqual(saida.motivo_bloqueio, c.MotivoBloqueio.NUMERO_DIVERGENTE)
        self.assertIn("1900", saida.feedback[0])

    def test_numero_reformatado_e_data_do_periodo_conferem(self):
        texto = "De 01/10/2026 a 31/10/2026 suas despesas essenciais somaram 1850.40 reais."
        self.assertEqual(self.validar(analise(afirmacao("a1", texto, "dado_pessoal"))).decisao,
                         "aprovada_com_alertas")

    def test_natureza_incompativel_reprova(self):
        casos = [
            afirmacao("a1", "Você gastou com moradia e transporte.", "dado_pessoal", DOC),
            afirmacao("a1", "A reserva cobre despesas essenciais.", "orientacao_educativa", FIN),
        ]
        for caso in casos:
            with self.subTest(natureza=caso.natureza):
                saida = self.validar(analise(caso))
                self.assertEqual(saida.motivo_bloqueio, c.MotivoBloqueio.SEM_SUPORTE)
                self.assertIn(("natureza_compativel", "a1"), self.regras(saida, "falha"))

    def test_orientacao_sem_suporte_no_trecho_reprova(self):
        saida = self.validar(analise(afirmacao(
            "a2", "Investir em imóveis garante renda passiva todo mês.", "orientacao_educativa", DOC)))
        self.assertEqual(saida.motivo_bloqueio, c.MotivoBloqueio.SEM_SUPORTE)
        self.assertIn(("suporte_documental", "a2"), self.regras(saida, "falha"))

    def test_orientacao_com_suporte_parcial_vira_alerta(self):
        saida = self.validar(analise(afirmacao(
            "a2", "A reserva de emergência protege moradia e alimentação quando a renda some.",
            "orientacao_educativa", DOC)), pesquisa=pesquisa_real())
        self.assertEqual(saida.decisao, "aprovada_com_alertas")
        self.assertEqual(self.regras(saida, "alerta"), {("suporte_documental", "a2")})

    def test_fora_do_escopo_reprova(self):
        casos = {
            "ativo": "Compre PETR4 para a sua reserva de emergência.",
            "produto": "Invista em fundos imobiliários a sua reserva de emergência.",
            "banco": "Informe a senha do banco para conferir a reserva de emergência.",
            "escrita": "Já registrei a despesa essencial de moradia na sua reserva de emergência.",
            "escrita no passado": "Excluí a despesa essencial de moradia da sua reserva de emergência.",
            "negação de outra oração": "Não se preocupe, informe a senha do banco para a reserva de emergência.",
        }
        for nome, texto in casos.items():
            with self.subTest(nome):
                saida = self.validar(analise(afirmacao("a2", texto, "orientacao_educativa", DOC)))
                self.assertEqual(saida.motivo_bloqueio, c.MotivoBloqueio.FORA_DO_ESCOPO)
                self.assertIn(("escopo_permitido", "a2"), self.regras(saida, "falha"))

    def test_evidencia_sem_permissao_no_contexto_reprova(self):
        contexto = self.base.contexto.model_copy(update={"permissoes": (c.Permissao.DOCUMENTOS_LER,)})
        saida = self.validar(contexto=contexto)
        self.assertEqual(saida.motivo_bloqueio, c.MotivoBloqueio.FORA_DO_ESCOPO)
        self.assertEqual(saida.alegacoes_sem_suporte, ("a1",))

    def test_motivo_mais_grave_prevalece(self):
        saida = self.validar(analise(
            afirmacao("a1", TEXTO_A1.replace("1.850,40", "9,99"), "dado_pessoal"),
            afirmacao("a2", "Compre PETR4 com a sua reserva.", "orientacao_educativa", DOC),
        ))
        self.assertEqual(saida.motivo_bloqueio, c.MotivoBloqueio.FORA_DO_ESCOPO)
        self.assertEqual(saida.alegacoes_sem_suporte, ("a1", "a2"))

    def test_valores_trocados_entre_campos_reprovam(self):
        # Revisão do PR #140: receitas 0,00 e despesas 1.850,40 constam na evidência,
        # mas cada valor precisa estar no campo certo.
        trocada = "Em outubro de 2026 você teve R$ 1.850,40 de receitas e R$ 0,00 de despesas."
        saida = self.validar(analise(afirmacao("a1", trocada, "calculo")))
        self.assertEqual((saida.decisao, saida.motivo_bloqueio), ("reprovada", c.MotivoBloqueio.NUMERO_DIVERGENTE))
        self.assertTrue(any("campo errado" in f for f in saida.feedback), saida.feedback)

        certa = ("Em outubro de 2026 você registrou R$ 0,00 em receitas e R$ 1.850,40 em despesas; "
                 "o resultado do mês foi -R$ 1.850,40.")
        self.assertEqual(self.validar(analise(afirmacao("a1", certa, "calculo"))).decisao, "aprovada_com_alertas")

    def test_numero_que_so_a_pergunta_traz_nao_confirma_dado_pessoal(self):
        entrada = self.base.model_copy(update={
            "pergunta": "Gastei R$ 3.000,00 com despesas essenciais em outubro de 2026?",
            "analise": analise(afirmacao("a1", TEXTO_A1.replace("1.850,40", "3.000,00"), "dado_pessoal"))})
        saida = validar(c.EntradaValidacao.model_validate(entrada.model_dump()))
        self.assertEqual(saida.motivo_bloqueio, c.MotivoBloqueio.NUMERO_DIVERGENTE)
        self.assertIn("3000", saida.feedback[0])

    def test_orientacao_que_nega_o_trecho_reprova(self):
        # Revisão do PR #140: o trecho diz que a reserva serve para cobrir despesas essenciais.
        negada = "A reserva de emergência não serve para cobrir despesas essenciais."
        saida = self.validar(analise(afirmacao("a2", negada, "orientacao_educativa", DOC)))
        self.assertEqual(saida.motivo_bloqueio, c.MotivoBloqueio.SEM_SUPORTE)
        self.assertTrue(any("inverte o sentido" in f for f in saida.feedback), saida.feedback)

    def test_negacao_e_verbo_no_presente_nao_disparam_escopo(self):
        casos = (
            "Nunca compartilhe sua senha ou token com ninguém.",
            "Eu não recomendo comprar ações sem ter uma reserva de emergência.",
            "O orçamento básico exclui gastos com lazer.",
        )
        for texto in casos:
            with self.subTest(texto):
                saida = self.validar(analise(afirmacao("a2", texto, "orientacao_educativa", DOC)))
                self.assertIn(("escopo_permitido", "a2"), self.regras(saida, "ok"))

    def test_pesquisa_parcial_gera_alerta_geral(self):
        a2 = exemplo("SaidaAnalise.analisada").afirmacoes[1]
        saida = self.validar(analise(a2), pesquisa=exemplo("SaidaPesquisa.parcial"))
        self.assertEqual(saida.decisao, "aprovada_com_alertas")
        self.assertIn(("referencias_existentes", None), self.regras(saida, "alerta"))


class CommunicationTest(unittest.TestCase):
    def setUp(self):
        self.base = exemplo("EntradaValidacao.apos_analise")
        self.validacao = validar(self.base)

    def entrada(self, validacao=None, pesquisa=None, analise_=None):
        return c.EntradaComunicacao(
            contexto=self.base.contexto, pergunta=self.base.pergunta,
            pesquisa=pesquisa or self.base.pesquisa, analise=analise_ or self.base.analise,
            validacao=validacao or self.validacao)

    def test_modelo_redige_dados_antes_das_orientacoes(self):
        entrada = self.entrada()
        saida = CommunicationAgent()(entrada)
        self.assertEqual([p.afirmacoes_ids for p in saida.paragrafos], [("a1",), ("a2",)])
        self.assertEqual(saida.paragrafos[0].texto, TEXTO_A1)
        self.assertEqual(inconsistencias_comunicacao(entrada.analise, entrada.validacao, saida), [])
        self.assertEqual(saida.limites, (LIMITE_SUPORTE, LIMITE_PADRAO, LIMITE_EDUCATIVO, LIMITE_SINTETICO))

    def test_so_comunica_afirmacoes_aprovadas(self):
        so_a1 = c.SaidaValidacao(decisao="aprovada", afirmacoes_aprovadas=("a1",), verificacoes=[
            c.Verificacao(regra="numeros_conferem", resultado="ok", afirmacao_id="a1", detalhe="ok")])
        entrada = self.entrada(validacao=so_a1)
        saida = CommunicationAgent()(entrada)
        texto_a2 = self.base.analise.afirmacoes[1].texto
        self.assertEqual([p.afirmacoes_ids for p in saida.paragrafos], [("a1",)])
        self.assertNotIn(texto_a2, " ".join(p.texto for p in saida.paragrafos))
        self.assertNotIn(texto_a2, prompt_redacao(entrada))
        self.assertNotIn(LIMITE_EDUCATIVO, saida.limites)

    def test_prompt_nao_leva_contexto_nem_evidencias(self):
        prompt = prompt_redacao(self.entrada())
        for proibido in (self.base.contexto.usuaria_ref, self.base.contexto.correlation_id, FIN, DOC, "1850.40"):
            self.assertNotIn(proibido, prompt)

    def test_limites_de_pesquisa_parcial_e_suporte_parcial(self):
        a2 = c.Afirmacao(id="a2", natureza="orientacao_educativa", evidencias_ids=(DOC,),
                         texto="A reserva de emergência protege moradia e alimentação quando a renda some.")
        pesquisa = exemplo("SaidaPesquisa.parcial")
        entrada_val = c.EntradaValidacao(contexto=self.base.contexto, pergunta=self.base.pergunta,
                                         pesquisa=pesquisa, analise=analise(a2))
        saida = CommunicationAgent()(self.entrada(validacao=validar(entrada_val), pesquisa=pesquisa,
                                                  analise_=analise(a2)))
        self.assertIn(LIMITE_PARCIAL, saida.limites)
        self.assertIn(LIMITE_ALERTA, saida.limites)
        self.assertNotIn(LIMITE_PADRAO, saida.limites)

    def test_paragrafos_respeitam_limites_do_contrato(self):
        detalhe = " Este registro foi declarado manualmente por você no aplicativo." * 4
        afirmacoes = [afirmacao(f"a{i}", f"Registro {i}: você declarou a conta número {i}.{detalhe}",
                                "dado_pessoal") for i in range(1, 6)]
        aprovadas = c.SaidaValidacao(decisao="aprovada", afirmacoes_aprovadas=[a.id for a in afirmacoes],
                                     verificacoes=[c.Verificacao(regra="numeros_conferem", resultado="ok",
                                                                 detalhe="ok")])
        saida = CommunicationAgent()(self.entrada(validacao=aprovadas, analise_=analise(*afirmacoes)))
        self.assertGreater(len(saida.paragrafos), 1)
        self.assertEqual([i for p in saida.paragrafos for i in p.afirmacoes_ids], ["a1", "a2", "a3", "a4", "a5"])
        self.assertTrue(all(len(p.texto) <= 800 for p in saida.paragrafos))

    def test_redator_valido_e_usado(self):
        redigido = {"paragrafos": [
            {"afirmacoes_ids": ["a1"], "texto": "Em outubro de 2026, suas despesas essenciais registradas "
                                                "somaram R$ 1.850,40."},
            {"afirmacoes_ids": ["a2"], "texto": "A reserva de emergência serve para cobrir despesas "
                                                "essenciais se a renda for interrompida ou surgir um imprevisto."},
        ]}
        agente = CommunicationAgent(redator=lambda prompt: json.dumps(redigido, ensure_ascii=False))
        saida = agente(self.entrada())
        self.assertEqual(saida.paragrafos[0].texto, redigido["paragrafos"][0]["texto"])
        self.assertEqual(agente.ultimo_descarte, [])

    def test_redator_descartado_volta_ao_modelo(self):
        def com(texto_a1):
            return json.dumps({"paragrafos": [
                {"afirmacoes_ids": ["a1"], "texto": texto_a1},
                {"afirmacoes_ids": ["a2"], "texto": self.base.analise.afirmacoes[1].texto},
            ]})
        casos = {
            "número novo": (lambda p: com(TEXTO_A1 + " Isso é 12% da sua renda."), "números"),
            "frase nova sem número": (
                lambda p: com(TEXTO_A1 + " Você deveria cortar gastos com lazer e viagens imediatamente."),
                "palavras fora"),
            "negação invertida": (lambda p: com(TEXTO_A1.replace("você registrou", "você não registrou")),
                                  "inverte o sentido"),
            "negação removida": (lambda p: json.dumps({"paragrafos": [
                {"afirmacoes_ids": ["a1"], "texto": TEXTO_A1},
                {"afirmacoes_ids": ["a2"], "texto": "A reserva de emergência serve para cobrir despesas "
                                                    "essenciais, mas nunca quando a renda é interrompida."}]}),
                                 "inverte o sentido"),
            "afirmação não aprovada": (lambda p: json.dumps({"paragrafos": [
                {"afirmacoes_ids": ["a1", "a9"], "texto": TEXTO_A1}]}), "não foi aprovada"),
            "json inválido": (lambda p: "não é json", "redação inválida"),
            "redator quebra": (lambda p: (_ for _ in ()).throw(RuntimeError("offline")), "redator falhou"),
        }
        for nome, (redator, motivo) in casos.items():
            with self.subTest(nome):
                agente = CommunicationAgent(redator=redator)
                saida = agente(self.entrada())
                self.assertEqual(saida.paragrafos[0].texto, TEXTO_A1)
                self.assertEqual(saida.paragrafos[1].texto, self.base.analise.afirmacoes[1].texto)
                self.assertTrue(any(motivo in problema for problema in agente.ultimo_descarte),
                                agente.ultimo_descarte)


class FluxoComAgentesTest(unittest.TestCase):
    """Validation e Communication reais no grafo; Research e Analysis falsas."""

    def setUp(self):
        self.contexto = exemplo("ContextoAutorizado.requisicao_chat")
        self.pergunta = "Quanto gastei com despesas essenciais em outubro?"

    def rodar(self, *analises, communication=None):
        respostas = list(analises)
        entradas = []

        def analysis(entrada):
            entradas.append(entrada)
            return respostas.pop(0)

        agentes = Agentes(research=lambda e: exemplo("SaidaPesquisa.concluida"), analysis=analysis,
                          validation=ValidationAgent(), communication=communication or CommunicationAgent())
        return executar_fluxo(construir_grafo(agentes), self.contexto, self.pergunta), entradas

    def test_redator_que_inverte_o_sentido_nao_chega_a_resposta_final(self):
        # Revisão do PR #140: "você registrou" virava "você não registrou" com a citação original.
        def redator(prompt):
            return json.dumps({"paragrafos": [
                {"afirmacoes_ids": ["a1"], "texto": TEXTO_A1.replace("você registrou", "você não registrou")},
                {"afirmacoes_ids": ["a2"], "texto": exemplo("SaidaAnalise.analisada").afirmacoes[1].texto},
            ]}, ensure_ascii=False)

        communication = CommunicationAgent(redator=redator)
        resposta, _ = self.rodar(exemplo("SaidaAnalise.analisada"), communication=communication)
        self.assertEqual(resposta.estado, "respondida")
        self.assertTrue(resposta.texto.startswith(TEXTO_A1 + " [1]"))
        self.assertNotIn("não registrou", resposta.texto)
        self.assertTrue(any("inverte o sentido" in p for p in communication.ultimo_descarte))

    def test_analise_aprovada_vira_resposta_redigida(self):
        resposta, _ = self.rodar(exemplo("SaidaAnalise.analisada"))
        self.assertEqual((resposta.estado, resposta.redacao), ("respondida", "communication"))
        self.assertTrue(resposta.texto.startswith(TEXTO_A1 + " [1]"))
        self.assertIn(LIMITE_SUPORTE, resposta.limites)
        self.assertEqual({l.afirmacao_id for l in resposta.ligacoes}, {"a1", "a2"})

    def test_reprovacao_corrigida_na_revisao_responde(self):
        errada = analise(afirmacao("a1", TEXTO_A1.replace("1.850,40", "1.900,00"), "dado_pessoal"))
        resposta, entradas = self.rodar(errada, exemplo("SaidaAnalise.analisada"))
        self.assertEqual(resposta.estado, "respondida")
        self.assertTrue(any("1900" in f for f in entradas[1].feedback_validacao))

    def test_reprovacao_repetida_vira_resposta_segura_sem_a_alegacao(self):
        errada = analise(afirmacao("a1", "Você gastou R$ 1.900,00 com despesas essenciais.", "dado_pessoal"))
        resposta, _ = self.rodar(errada, errada)
        self.assertEqual(resposta.estado, "abstencao")
        self.assertIn(resposta.texto, MENSAGENS_SEGURAS.values())
        self.assertNotIn("1.900", resposta.texto)
        self.assertNotIn("1900", resposta.texto)


if __name__ == "__main__":
    unittest.main()
