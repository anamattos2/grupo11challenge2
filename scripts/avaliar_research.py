"""Avalia o planejamento e a segurança do Research Agent (S4-02 / #76).

Uso, na raiz do repositório, com o extra ``agents`` (e ``llm`` para Ollama):

    python scripts/avaliar_research.py                        # planejador por regras
    python scripts/avaliar_research.py --planejador ollama    # LLM local
    python scripts/avaliar_research.py --gravar-baseline      # atualiza a baseline versionada

O resultado completo vai para ``.runtime/avaliacoes/`` (não versionado), com
versão do código, modelo e parâmetros, como pede evaluations/README.md.
Todos os dados são fictícios.
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
CASOS = RAIZ / "evaluations" / "research-agent" / "casos.json"
BASELINE = RAIZ / "evaluations" / "research-agent" / "baseline-regras.json"


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    from finance_ai.agents.avaliacao import avaliar
    from finance_ai.agents.ferramentas import criar_ferramentas
    from finance_ai.agents.planejador import PlanejadorLLM, modelo_ollama

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--planejador", choices=["regras", "ollama"], default="regras")
    parser.add_argument("--modelo", help="modelo do Ollama (padrão: OLLAMA_MODEL ou qwen2.5:7b)")
    parser.add_argument("--gravar-baseline", action="store_true", help="grava o resumo como baseline (só regras)")
    args = parser.parse_args()

    modelo = None
    if args.planejador == "ollama":
        modelo = args.modelo or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        criar = lambda r, f: PlanejadorLLM(modelo_ollama(modelo), criar_ferramentas(r, f))  # noqa: E731
    else:
        criar = lambda r, f: None  # noqa: E731 - None = PlanejadorPorRegras
    try:
        relatorio = avaliar(CASOS, criar, args.planejador)
    except ImportError as erro:
        parser.error(str(erro))

    print(f"{'caso':28} {'categoria':18} {'exata':>6} {'período':>8} {'status':>7} {'isol.':>5}  ferramentas")
    for r in relatorio.por_caso:
        marca = lambda v: "-" if v is None else ("ok" if v else "ERRO")  # noqa: E731
        ferramentas = "BLOQUEADO" if r.plano_bloqueado else ", ".join(r.ferramentas) or "(nenhuma)"
        print(f"{r.id:28} {r.categoria:18} {marca(r.selecao_exata):>6} {marca(r.periodo_correto):>8} "
              f"{marca(r.status_correto):>7} {r.violacoes_isolamento:>5}  {ferramentas}")
    print()
    for chave, valor in relatorio.resumo().items():
        print(f"  {chave:22} {valor}")

    meta = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": _commit(),
            "casos_versao": json.loads(CASOS.read_text(encoding="utf-8"))["versao"],
            "planejador": args.planejador, "modelo": modelo, "temperatura": 0 if modelo else None,
            "python": platform.python_version()}
    destino = RAIZ / ".runtime" / "avaliacoes"
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"research-{args.planejador}-{datetime.now():%Y%m%d-%H%M%S}.json"
    arquivo.write_text(json.dumps({"meta": meta, "resumo": relatorio.resumo(),
                                   "por_caso": [asdict(r) for r in relatorio.por_caso]},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nRelatório completo: {arquivo.relative_to(RAIZ)}")

    if args.gravar_baseline:
        if args.planejador != "regras":
            parser.error("a baseline versionada é a do planejador por regras (determinística)")
        resumo = relatorio.resumo()
        resumo.pop("latencia_media_ms")  # depende da máquina
        BASELINE.write_text(json.dumps({"casos_versao": meta["casos_versao"], **resumo},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline gravada em {BASELINE.relative_to(RAIZ)}")
    return 1 if relatorio.violacoes_isolamento else 0


if __name__ == "__main__":
    sys.exit(main())
