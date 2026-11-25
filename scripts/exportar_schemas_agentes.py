"""Exporta os contratos dos agentes como JSON Schema e o diagrama do grafo (S4-01 / #75).

Uso, na raiz do repositório, com o extra ``agents`` instalado:

    python scripts/exportar_schemas_agentes.py          # grava os arquivos
    python scripts/exportar_schemas_agentes.py --check  # só confere (CI)

Os modelos Pydantic em ``finance_ai/agents/contratos.py`` são a fonte da
verdade. Os ``.schema.json`` servem a quem não usa Python (frontend, revisão,
ferramentas de validação) e permitem ver mudanças de contrato no diff do PR.
O ``fluxo.mmd`` é desenhado pelo LangGraph a partir do grafo real.
"""

import argparse
import json
from pathlib import Path
import sys

RAIZ_CONTRATOS = Path(__file__).resolve().parents[1] / "contracts" / "agentes"
DESTINO = RAIZ_CONTRATOS / "schemas"
DIAGRAMA = RAIZ_CONTRATOS / "fluxo.mmd"
BASE_ID = "https://github.com/anamattos2/grupo11challenge2/contracts/agentes/schemas/"


def gerar() -> dict[str, str]:
    from finance_ai.agents.contratos import CONTRATOS_EXPORTADOS, VERSAO_CONTRATOS

    arquivos = {}
    for nome, modelo in CONTRATOS_EXPORTADOS.items():
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{BASE_ID}{nome}.schema.json",
            "x-versao-contrato": VERSAO_CONTRATOS,
            **modelo.model_json_schema(mode="validation"),
        }
        texto = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        arquivos[f"{nome}.schema.json"] = texto
    return arquivos


def gerar_diagrama() -> str:
    from finance_ai.agents.grafo import diagrama_mermaid

    return diagrama_mermaid().rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="falha se os arquivos estiverem desatualizados")
    args = parser.parse_args()
    arquivos = gerar()
    if args.check:
        divergentes = [
            nome for nome, texto in arquivos.items()
            if not (DESTINO / nome).is_file() or (DESTINO / nome).read_text(encoding="utf-8") != texto
        ]
        sobrando = sorted(p.name for p in DESTINO.glob("*.schema.json") if p.name not in arquivos)
        if not DIAGRAMA.is_file() or DIAGRAMA.read_text(encoding="utf-8") != gerar_diagrama():
            divergentes.append(DIAGRAMA.name)
        if divergentes or sobrando:
            print("Schemas desatualizados; rode scripts/exportar_schemas_agentes.py", file=sys.stderr)
            for nome in divergentes + sobrando:
                print(f"  {nome}", file=sys.stderr)
            return 1
        print(f"OK: {len(arquivos)} schemas e o diagrama do fluxo atualizados.")
        return 0
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, texto in arquivos.items():
        (DESTINO / nome).write_text(texto, encoding="utf-8")
    DIAGRAMA.write_text(gerar_diagrama(), encoding="utf-8")
    print(f"{len(arquivos)} schemas e {DIAGRAMA.name} gravados em {RAIZ_CONTRATOS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
