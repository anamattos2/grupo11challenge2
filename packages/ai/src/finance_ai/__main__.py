"""Comando de verificação da instalação, sem acesso a dados ou modelos."""

import json
from importlib.metadata import version


def main() -> None:
    print(json.dumps({
        "package": "grupo11-finance-ai",
        "version": version("grupo11-finance-ai"),
        "status": "estrutura_inicial",
        "componentes_implementados": [],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
