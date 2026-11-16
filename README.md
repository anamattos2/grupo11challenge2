# grupo11challenge2

PWA de gestão financeira para mulheres em início de carreira, com foco na
construção de uma reserva de emergência. Projeto da Residência em Inteligência
Artificial — Desafio 02, Grupo 11.

## Planejamento técnico

- [Escopo e requisitos do MVP](docs/definicao/escopo-requisitos.md)
- [Cenário, público, problema e Essential Question](docs/definicao/cenario-problema.md)
- [Como contribuir: branches, commits, revisão e definição de pronto](CONTRIBUTING.md)
- [Política de versionamento e preservação de pesquisa](docs/desenvolvimento/versionamento.md)
- [Arquitetura inicial e responsabilidades](docs/arquitetura/arquitetura-inicial.md)
- [Ambiente de desenvolvimento e organização do monorepositório](docs/desenvolvimento/ambiente.md)
- [Experimentos RAG preservados](experiments/rag/README.md)
- [Issue #55 — BASE-01](https://github.com/anamattos2/grupo11challenge2/issues/55)

A arquitetura descreve o sistema a construir. Os notebooks e scripts existentes
são experimentos de referência e não representam funcionalidades do produto
concluídas. A implementação e a organização do monorepositório serão realizadas
incrementalmente em issues e pull requests próprios.

## Executar a base inicial

Com Python 3.12 a 3.14, na raiz do repositório:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --editable ./packages/ai
.venv/bin/python -m pip check
.venv/bin/python -m finance_ai
python3 scripts/verificar_legado.py
```

Esta verificação instala a estrutura inicial do pacote de IA, sem modelos ou
serviços externos. Frontend, backend e funcionalidades financeiras ainda serão
implementados. Instruções para Windows, configuração e limites estão no
[guia do ambiente](docs/desenvolvimento/ambiente.md).
