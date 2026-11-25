"""Avalia o Analysis Agent (S4-03 / #77) com casos fictícios.

Uso, na raiz do repositório, com o extra ``agents`` (e ``llm`` para Ollama):

    python scripts/avaliar_analysis.py                     # redator por regras
    python scripts/avaliar_analysis.py --redator ollama    # LLM local redige, código confere
    python scripts/avaliar_analysis.py --gravar-baseline   # atualiza a baseline versionada

O resultado completo vai para ``.runtime/avaliacoes/`` (não versionado).
Sai com código 1 se algum número ficar sem origem nas evidências.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "evaluations" / "analysis-agent" / "casos.json"
BASELINE = RAIZ / "evaluations" / "analysis-agent" / "baseline-regras.json"


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    from finance_ai.agents.analysis import RedatorLLM
    from finance_ai.agents.avaliacao_analysis import avaliar
    from finance_ai.agents.planejador import modelo_ollama

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--redator", choices=["regras", "ollama"], default="regras")
    parser.add_argument("--modelo", help="modelo do Ollama (padrão: OLLAMA_MODEL ou qwen2.5:7b)")
    parser.add_argument("--gravar-baseline", action="store_true", help="grava o resumo como baseline (só regras)")
    args = parser.parse_args()

    modelo, redator = None, None
    if args.redator == "ollama":
        modelo = args.modelo or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        try:
            redator = RedatorLLM(modelo_ollama(modelo))
        except ImportError as erro:
            parser.error(str(erro))
    relatorio = avaliar(CASOS, redator, args.redator)

    marca = lambda v: "-" if v is None else ("ok" if v else "ERRO")  # noqa: E731
    print(f"{'caso':28} {'status':20} {'st.':>4} {'calc.':>5} {'lac.':>5} {'val.':>5} {'rastr.':>6} sem origem")
    for r in relatorio.por_caso:
        print(f"{r.id:28} {str(r.status):20} {marca(r.status_correto):>4} {marca(r.pedido_correto):>5} "
              f"{marca(r.lacunas_corretas):>5} {marca(r.valores_corretos):>5} "
              f"{r.rastreaveis}/{r.afirmacoes:<4} {', '.join(r.numeros_sem_origem) or '-'}")
    print()
    for chave, valor in relatorio.resumo().items():
        print(f"  {chave:24} {valor}")

    meta = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": _commit(),
            "casos_versao": json.loads(CASOS.read_text(encoding="utf-8"))["versao"],
            "redator": args.redator, "modelo": modelo, "temperatura": 0 if modelo else None,
            "python": platform.python_version()}
    destino = RAIZ / ".runtime" / "avaliacoes"
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"analysis-{args.redator}-{datetime.now():%Y%m%d-%H%M%S}.json"
    arquivo.write_text(json.dumps({"meta": meta, "resumo": relatorio.resumo(),
                                   "por_caso": [asdict(r) for r in relatorio.por_caso]},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nRelatório completo: {arquivo.relative_to(RAIZ)}")

    if args.gravar_baseline:
        if args.redator != "regras":
            parser.error("a baseline versionada é a do redator por regras (determinística)")
        resumo = relatorio.resumo()
        resumo.pop("latencia_media_ms")
        BASELINE.write_text(json.dumps({"casos_versao": meta["casos_versao"], **resumo},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline gravada em {BASELINE.relative_to(RAIZ)}")
    return 1 if relatorio.resumo()["numeros_sem_origem"] else 0


if __name__ == "__main__":
    sys.exit(main())
