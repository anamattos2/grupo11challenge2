"""Contratos dos agentes (S4-01 / #75): exemplos, schemas e invariantes.

Todos os dados são fictícios.
"""
import importlib.util
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from finance_ai.agents import contratos as c

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLOS = RAIZ / "contracts" / "agentes" / "exemplos"
SCHEMAS = RAIZ / "contracts" / "agentes" / "schemas"


def carregar(pasta: str) -> list[tuple[Path, dict]]:
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted((EXEMPLOS / pasta).glob("*.json"))]


class ExemplosTest(unittest.TestCase):
    def test_todo_schema_tem_exemplo_valido(self):
        cobertos = {d["schema"] for _, d in carregar("validos")}
        self.assertEqual(cobertos, set(c.CONTRATOS_EXPORTADOS))

    def test_exemplos_validos_sao_aceitos(self):
        for caminho, dados in carregar("validos"):
            with self.subTest(exemplo=caminho.name):
                self.assertEqual(caminho.name, f"{dados['schema']}.{dados['caso']}.json")
                c.CONTRATOS_EXPORTADOS[dados["schema"]].model_validate(dados["documento"])

    def test_exemplos_invalidos_sao_recusados_pelo_motivo_esperado(self):
        exemplos = carregar("invalidos")
        self.assertGreaterEqual(len(exemplos), 10)
        for caminho, dados in exemplos:
            with self.subTest(exemplo=caminho.name):
                with self.assertRaises(ValidationError) as ctx:
                    c.CONTRATOS_EXPORTADOS[dados["schema"]].model_validate(dados["documento"])
                tipos = {erro["type"] for erro in ctx.exception.errors()}
                self.assertIn(dados["erro_esperado"], tipos)

    def test_json_roundtrip_preserva_conteudo(self):
        for caminho, dados in carregar("validos"):
            with self.subTest(exemplo=caminho.name):
                modelo = c.CONTRATOS_EXPORTADOS[dados["schema"]]
                obj = modelo.model_validate(dados["documento"])
                self.assertEqual(modelo.model_validate_json(obj.model_dump_json()), obj)


class SchemasExportadosTest(unittest.TestCase):
    def test_arquivos_estao_sincronizados_com_os_modelos(self):
        spec = importlib.util.spec_from_file_location("exportar", RAIZ / "scripts" / "exportar_schemas_agentes.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        gerados = modulo.gerar()
        self.assertEqual(sorted(gerados), sorted(p.name for p in SCHEMAS.glob("*.schema.json")))
        for nome, texto in gerados.items():
            with self.subTest(schema=nome):
                self.assertEqual((SCHEMAS / nome).read_text(encoding="utf-8"), texto,
                                 "rode scripts/exportar_schemas_agentes.py")

    def test_schemas_proibem_campos_extras(self):
        schema = json.loads((SCHEMAS / "ChamadaFerramenta.schema.json").read_text(encoding="utf-8"))
        self.assertIs(schema["additionalProperties"], False)
        self.assertIs(schema["$defs"]["ParametrosFinanceiros"]["additionalProperties"], False)


class InvariantesTest(unittest.TestCase):
    """Regras que os critérios de aceite pedem de forma explícita."""

    def setUp(self):
        dados = json.loads((EXEMPLOS / "validos" / "SaidaPesquisa.concluida.json").read_text(encoding="utf-8"))
        self.pesquisa = c.SaidaPesquisa.model_validate(dados["documento"])

    def test_evidencias_tem_tipo_origem_id_e_localizacao(self):
        for evidencia in self.pesquisa.evidencias:
            self.assertIn(evidencia.tipo, ("documental", "financeira"))
            self.assertTrue(evidencia.id.startswith("doc:" if evidencia.tipo == "documental" else "fin:"))
            self.assertIsNotNone(evidencia.origem)
            self.assertIsNotNone(evidencia.localizacao)

    def test_nenhum_contrato_aceita_identidade_da_usuaria_fora_do_contexto(self):
        # Só o ContextoAutorizado (montado pelo backend) tem campo de usuária.
        for nome, modelo in c.CONTRATOS_EXPORTADOS.items():
            schema = modelo.model_json_schema()
            definicoes = {nome: schema, **schema.get("$defs", {})}
            for definicao, corpo in definicoes.items():
                campos = corpo.get("properties", {})
                com_usuaria = [campo for campo in campos if "usuaria" in campo]
                esperado = ["usuaria_ref"] if definicao == "ContextoAutorizado" else []
                self.assertEqual(com_usuaria, esperado, f"{nome} → {definicao}")

    def test_contratos_sao_imutaveis(self):
        with self.assertRaises(ValidationError):
            self.pesquisa.status = "falha"

    def test_papeis_tem_saidas_distintas(self):
        saidas = [c.SaidaPesquisa, c.SaidaAnalise, c.SaidaValidacao, c.SaidaComunicacao]
        campos = [frozenset(m.model_fields) - {"versao"} for m in saidas]
        self.assertEqual(len(set(campos)), 4)
        # Só a Research produz evidências; só a Analysis produz afirmações;
        # só a Validation decide; só a Communication escreve texto à usuária.
        self.assertEqual([("evidencias" in f) for f in campos], [True, False, False, False])
        self.assertEqual([("afirmacoes" in f) for f in campos], [False, True, False, False])
        self.assertEqual([("decisao" in f) for f in campos], [False, False, True, False])
        self.assertEqual([("texto" in f) for f in campos], [False, False, False, True])


if __name__ == "__main__":
    unittest.main()
