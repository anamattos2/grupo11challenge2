"""Testes combinatórios exaustivos do fluxo dos agentes (S4-01 / #75).

Em vez de um teste por cenário, cada agente recebe um cardápio de
comportamentos: corretos, inconsistentes (ids que não existem), maliciosos
(número inventado, afirmação não aprovada) e quebrados (exceção, timeout,
saída fora do contrato). O grafo roda com TODAS as combinações e, em cada
execução, conferimos as invariantes que nunca podem ser violadas:

1. ``executar_fluxo`` nunca lança exceção e sempre devolve ``RespostaFinal`` válida.
2. Resposta ``respondida`` só expressa afirmações aprovadas que existem na
   análise, com evidências que existem na pesquisa, cobre todas as aprovadas e
   não traz número que não esteja nelas.
3. Qualquer outro desfecho usa texto fixo, sem fontes, ligações nem trechos da análise.
4. O fluxo termina: limites de chamadas por agente são respeitados.
5. Falha de pesquisa nunca vira "não encontrei" e nunca chama a Analysis.

Foi esse tipo de combinação (ids que não batem entre etapas) que a revisão do
PR #135 encontrou à mão. Dados fictícios.
"""
from __future__ import annotations

from collections import Counter
import itertools
import json
from pathlib import Path
import re
import unittest

from finance_ai.agents import contratos as c
from finance_ai.agents.fluxo import MENSAGEM_FALHA, MENSAGENS_SEGURAS, inconsistencias_comunicacao, numeros
from finance_ai.agents.grafo import Agentes, construir_grafo, executar_fluxo

VALIDOS = Path(__file__).resolve().parents[1] / "contracts" / "agentes" / "exemplos" / "validos"
SEGREDO = "detalhe-interno-que-nao-pode-vazar"
DOC_FANTASMA = "doc:" + "f" * 16


def exemplo(nome: str):
    dados = json.loads((VALIDOS / f"{nome}.json").read_text(encoding="utf-8"))
    return c.CONTRATOS_EXPORTADOS[dados["schema"]].model_validate(dados["documento"])


CONTEXTO = exemplo("ContextoAutorizado.requisicao_chat")


def complemento_setembro() -> c.SaidaPesquisa:
    fin = next(e for e in exemplo("SaidaPesquisa.concluida").evidencias if e.tipo == "financeira")
    setembro = fin.model_copy(update={"id": "fin:resumo_transacoes:aaaaaaaaaaaa"})
    return c.SaidaPesquisa(status="concluida", modo="prototipo_fixtures", evidencias=[setembro], chamadas=[
        c.RegistroChamada(ferramenta="financeiro.consultar", operacao="resumo_transacoes", pedido_id="c1",
                          status="ok", evidencias_ids=[setembro.id], duracao_ms=1)])


# --------------------------------------------------------------------------
# Cardápio de comportamentos. Cada fábrica devolve um agente novo por execução.
# --------------------------------------------------------------------------

def research(saida_inicial):
    def agente(entrada: c.EntradaPesquisa):
        if isinstance(saida_inicial, BaseException):
            raise saida_inicial
        if entrada.chamadas_solicitadas:
            return complemento_setembro()
        return saida_inicial
    return agente


RESEARCH = {
    "concluida": lambda: research(exemplo("SaidaPesquisa.concluida")),
    "parcial": lambda: research(exemplo("SaidaPesquisa.parcial")),
    "sem_evidencias": lambda: research(exemplo("SaidaPesquisa.sem_evidencias")),
    "sem_permissao": lambda: research(exemplo("SaidaPesquisa.sem_permissao")),
    "falha": lambda: research(exemplo("SaidaPesquisa.falha")),
    "excecao": lambda: research(RuntimeError(SEGREDO)),
    "timeout": lambda: research(TimeoutError(SEGREDO)),
    "contrato_invalido": lambda: research({"status": "concluida", "modo": "integrado"}),
}


def afirmacoes_validas(pesquisa: c.SaidaPesquisa) -> list[c.Afirmacao]:
    """Uma afirmação por evidência existente, com o número que a evidência traz."""
    afirmacoes = []
    for i, evidencia in enumerate(pesquisa.evidencias[:3], start=1):
        if evidencia.tipo == "financeira":
            texto = f"Você registrou {evidencia.valores.get('despesas')} em despesas no período."
            natureza = "dado_pessoal"
        else:
            texto = "A reserva de emergência cobre despesas essenciais em imprevistos."
            natureza = "orientacao_educativa"
        afirmacoes.append(c.Afirmacao(id=f"a{i}", texto=texto, natureza=natureza, evidencias_ids=[evidencia.id]))
    return afirmacoes


def analise_ok(entrada):
    return c.SaidaAnalise(status="analisada", afirmacoes=afirmacoes_validas(entrada.pesquisa))


def analise_fantasma(entrada):
    return c.SaidaAnalise(status="analisada", afirmacoes=[c.Afirmacao(
        id="a1", texto="Afirmação sem evidência real.", natureza="orientacao_educativa",
        evidencias_ids=[DOC_FANTASMA])])


def analise_calculo(entrada):
    return exemplo("SaidaAnalise.precisa_calculo")


def analise_calculo_depois_ok(entrada):
    return analise_ok(entrada) if entrada.calculos_ja_pedidos else analise_calculo(entrada)


def falhar(erro):
    def agente(entrada):
        raise erro
    return agente


ANALYSIS = {
    "ok": lambda: analise_ok,
    "evidencia_fantasma": lambda: analise_fantasma,
    "calculo_sempre": lambda: analise_calculo,
    "calculo_depois_ok": lambda: analise_calculo_depois_ok,
    "dados_insuficientes": lambda: (lambda e: exemplo("SaidaAnalise.dados_insuficientes")),
    "status_falha": lambda: (lambda e: c.SaidaAnalise(status="falha", codigo_erro="modelo_recusou")),
    "excecao": lambda: falhar(RuntimeError(SEGREDO)),
    "contrato_invalido": lambda: (lambda e: {"status": "analisada", "afirmacoes": []}),
}


def verificacoes(ids):
    return [c.Verificacao(regra="referencias_existentes", resultado="ok", detalhe="ok", afirmacao_id=i)
            for i in ids] or [c.Verificacao(regra="referencias_existentes", resultado="ok", detalhe="ok")]


def aprovar(ids_extras=()):
    def agente(entrada):
        ids = tuple(a.id for a in entrada.analise.afirmacoes) + tuple(ids_extras)
        return c.SaidaValidacao(decisao="aprovada", afirmacoes_aprovadas=ids, verificacoes=verificacoes(ids))
    return agente


def aprovar_so_a_primeira(entrada):
    primeira = entrada.analise.afirmacoes[0].id
    return c.SaidaValidacao(decisao="aprovada", afirmacoes_aprovadas=(primeira,), verificacoes=verificacoes([]))


def reprovar(entrada):
    return c.SaidaValidacao(
        decisao="reprovada", motivo_bloqueio="sem_suporte", feedback=["Cite a evidência correta."],
        alegacoes_sem_suporte=(entrada.analise.afirmacoes[0].id,),
        verificacoes=[c.Verificacao(regra="suporte_documental", resultado="falha", detalhe="sem suporte")])


def reprovar_depois_aprovar():
    chamadas = {"n": 0}

    def agente(entrada):
        chamadas["n"] += 1
        return reprovar(entrada) if chamadas["n"] == 1 else aprovar()(entrada)
    return agente


VALIDATION = {
    "aprova_tudo": lambda: aprovar(),
    "aprova_so_a_primeira": lambda: aprovar_so_a_primeira,
    "aprova_id_fantasma": lambda: aprovar(("a9",)),
    "reprova_sempre": lambda: reprovar,
    "reprova_depois_aprova": reprovar_depois_aprovar,
    "excecao": lambda: falhar(RuntimeError(SEGREDO)),
    "contrato_invalido": lambda: (lambda e: {"decisao": "aprovada"}),
}


def redigir(paragrafos):
    return c.SaidaComunicacao(paragrafos=[c.Paragrafo(afirmacoes_ids=ids, texto=texto) for ids, texto in paragrafos])


COMMUNICATION = {
    "fiel": lambda: (lambda e: redigir([((i,), next(a.texto for a in e.analise.afirmacoes if a.id == i))
                                        for i in e.validacao.afirmacoes_aprovadas])),
    "numero_inventado": lambda: (lambda e: redigir([(tuple(e.validacao.afirmacoes_aprovadas),
                                                     "Você gastou R$ 9.999,99 no período.")])),
    # Declara TODAS as afirmações da análise: só é aceito se todas foram aprovadas.
    "declara_todas": lambda: (lambda e: redigir([(tuple(a.id for a in e.analise.afirmacoes),
                                                  "Resumo de todas as afirmações.")])),
    "id_fantasma": lambda: (lambda e: redigir([(("a9",), "Texto sobre a afirmação a9.")])),
    "excecao": lambda: falhar(RuntimeError(SEGREDO)),
    "contrato_invalido": lambda: (lambda e: {"texto": "formato antigo", "fontes": []}),
}


class Espiao:
    """Conta chamadas e guarda entradas e saídas de um agente."""

    def __init__(self, agente):
        self.agente = agente
        self.entradas = []
        self.saidas = []

    def __call__(self, entrada):
        self.entradas.append(entrada)
        saida = self.agente(entrada)
        self.saidas.append(saida)
        return saida


class Atual:
    """O grafo é compilado uma vez; cada execução troca os agentes por trás dele."""

    def __init__(self):
        self.espioes = None

    def papel(self, indice):
        return lambda entrada: self.espioes[indice](entrada)


TEXTOS_SEGUROS = set(MENSAGENS_SEGURAS.values()) | {MENSAGEM_FALHA}


class FluxoExaustivoTest(unittest.TestCase):
    def test_todas_as_combinacoes_respeitam_as_invariantes(self):
        desfechos = Counter()
        combinacoes = list(itertools.product(RESEARCH, ANALYSIS, VALIDATION, COMMUNICATION))
        atual = Atual()
        grafo = construir_grafo(Agentes(*(atual.papel(i) for i in range(4))))
        for nomes in combinacoes:
            espioes = [Espiao(cardapio[nome]()) for cardapio, nome in
                       zip((RESEARCH, ANALYSIS, VALIDATION, COMMUNICATION), nomes)]
            atual.espioes = espioes
            try:
                resposta = executar_fluxo(grafo, CONTEXTO, "Pergunta fictícia")
            except Exception as erro:  # invariante 1
                self.fail(f"{nomes}: exceção escapou do fluxo: {erro!r}")
            with self.subTest(combinacao=nomes):
                self.verificar(nomes, resposta, *espioes)
            desfechos[(resposta.estado, resposta.motivo and resposta.motivo.value, resposta.redacao)] += 1

        # Garante que o cardápio exercita todos os desfechos relevantes.
        estados = {estado for estado, _, _ in desfechos}
        self.assertEqual(estados, {"respondida", "abstencao", "pedido_complemento", "falha"})
        motivos = {motivo for _, motivo, _ in desfechos if motivo}
        self.assertTrue({"sem_evidencias", "sem_permissao", "calculo_indisponivel", "validacao_reprovada",
                         "falha_pesquisa", "contrato_invalido", "tempo_esgotado"} <= motivos, motivos)
        self.assertEqual({r for (e, _, r) in desfechos if e == "respondida"}, {"communication", "literal"})
        self.assertGreater(len(combinacoes), 2000)

    def verificar(self, nomes, resposta, research_, analysis, validation, communication):
        # 1. Resposta sempre válida pelo próprio contrato.
        self.assertEqual(c.RespostaFinal.model_validate(resposta.model_dump()), resposta)
        self.assertNotIn(SEGREDO, resposta.model_dump_json())

        # 4. Terminação: limites de rodadas.
        self.assertLessEqual(len(research_.entradas), 2)
        self.assertLessEqual(len(analysis.entradas), 3)
        self.assertLessEqual(len(validation.entradas), 2)
        self.assertLessEqual(len(communication.entradas), 1)

        # 5. Pesquisa que falhou nunca vira "não encontrei" nem chega à Analysis.
        if nomes[0] in ("falha", "excecao", "timeout", "contrato_invalido"):
            self.assertEqual(resposta.estado, "falha")
            self.assertEqual(analysis.entradas, [])
        if nomes[0] == "sem_evidencias":
            self.assertEqual(resposta.motivo, c.MotivoEncerramento.SEM_EVIDENCIAS)
        if nomes[0] == "sem_permissao":
            self.assertEqual(resposta.motivo, c.MotivoEncerramento.SEM_PERMISSAO)

        if resposta.estado != "respondida":
            # 3. Texto fixo, nada derivado da análise.
            self.assertIn(resposta.texto, TEXTOS_SEGUROS)
            self.assertEqual((resposta.fontes, resposta.ligacoes, resposta.redacao), ((), (), None))
            return

        # 2. Resposta aprovada: tudo rastreável e só o que foi aprovado.
        entrada = communication.entradas[-1]
        pesquisa, analise, validacao = entrada.pesquisa, entrada.analise, entrada.validacao
        self.assertNotEqual(validacao.decisao, "reprovada")
        por_id = {a.id: a for a in analise.afirmacoes}
        aprovadas = set(validacao.afirmacoes_aprovadas)
        self.assertTrue(aprovadas <= set(por_id), "aprovou afirmação inexistente")
        self.assertEqual({l.afirmacao_id for l in resposta.ligacoes}, aprovadas, "cobertura das aprovadas")
        existentes = {e.id for e in pesquisa.evidencias}
        for ligacao in resposta.ligacoes:
            self.assertEqual(ligacao.evidencias_ids, por_id[ligacao.afirmacao_id].evidencias_ids)
        self.assertTrue({f.evidencia_id for f in resposta.fontes} <= existentes)
        sem_marcas = re.sub(r"\[\d+\]", "", resposta.texto)
        permitidos = set().union(*(numeros(por_id[i].texto) for i in aprovadas))
        self.assertTrue(numeros(sem_marcas) <= permitidos, f"número fora das afirmações: {sem_marcas}")
        if resposta.redacao == "literal":
            blocos = [re.sub(r"\s*\[\d+\]+$", "", b).strip() for b in resposta.texto.split("\n\n")]
            self.assertEqual(blocos, [por_id[i].texto for i in validacao.afirmacoes_aprovadas])
        else:
            # Redação da Communication só é usada se a checagem não achou nada.
            redacao = c.SaidaComunicacao.model_validate(communication.saidas[-1].model_dump())
            self.assertEqual(inconsistencias_comunicacao(analise, validacao, redacao), [])
            self.assertIn(nomes[3], ("fiel", "declara_todas"))


class StatusDaPesquisaExaustivoTest(unittest.TestCase):
    """Todas as combinações de até 3 chamadas, com e sem evidência."""

    def test_regra_do_status_em_todas_as_combinacoes(self):
        situacoes = ("sem_resultados", "negada", "erro")
        for tamanho in (1, 2, 3):
            for combinacao in itertools.product(situacoes, repeat=tamanho):
                for com_ok in (False, True):
                    with self.subTest(chamadas=combinacao, com_ok=com_ok):
                        lista = list(combinacao) + (["ok"] if com_ok else [])
                        status = c.status_da_pesquisa(com_ok, [type("R", (), {"status": s})() for s in lista])
                        if com_ok:
                            esperado = "parcial" if {"negada", "erro"} & set(lista) else "concluida"
                        elif "erro" in lista:
                            esperado = "falha"
                        elif "negada" in lista:
                            esperado = "sem_permissao"
                        else:
                            esperado = "sem_evidencias"
                        self.assertEqual(status, esperado)


if __name__ == "__main__":
    unittest.main()
