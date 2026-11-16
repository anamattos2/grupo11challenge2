# Evidências locais — BASE-02 / #56

Verificação realizada em 16/11/2026, na branch `chore-56-monorepo-ambiente`.
Base: commit `a733da0` da `main`, que já contém a arquitetura da #55 e a CI
de validação Python/notebooks. Este registro não substitui revisão e merge do PR.

## Preservação

- Inventário gerado do índice Git com 70 arquivos históricos e hashes dos blobs.
- `python3 scripts/verificar_legado.py` terminou com código 0:
  `OK: 70 arquivos históricos preservados no índice e no worktree.`
- Nenhum experimento, fonte, notebook, banco ou resultado foi movido ou excluído.
- Em repositório temporário, sem commits, o verificador aceitou um arquivo
  original e rejeitou alteração local, mudança adicionada ao índice e remoção
  do arquivo. O teste não modificou os arquivos históricos do projeto.

## Instalação limpa

Ambiente local: macOS, Python 3.14.6. Criado um novo ambiente virtual em
`/tmp/grupo11-56-venv`, sem aproveitar dependências de outro projeto.

```text
python3 -m venv /tmp/grupo11-56-venv
/tmp/grupo11-56-venv/bin/python -m pip install --no-cache-dir --editable ./packages/ai
Successfully installed grupo11-finance-ai-0.1.0

/tmp/grupo11-56-venv/bin/python -m pip check
No broken requirements found.

/tmp/grupo11-56-venv/bin/python -m finance_ai
{"package": "grupo11-finance-ai", "version": "0.1.0", "status": "estrutura_inicial", "componentes_implementados": []}
```

O comando `finance-ai` retornou a mesma saída. A execução por módulo também
funcionou fora do diretório do repositório, usando a instalação do ambiente.
A dependência de build `setuptools==80.9.0` foi obtida pela rede; a primeira
tentativa restrita falhou por resolução de DNS e a instalação foi repetida com
autorização de rede. Nenhum modelo ou banco foi carregado.

## Documentação e verificações adicionais

- Links Markdown locais e pares de blocos de código conferidos.
- Sintaxe dos arquivos Python e estrutura JSON dos notebooks conferidas sem
  executar os experimentos.
- `git diff --check` sem erros nos arquivos rastreados modificados.
- CI estendida no job existente `python-and-notebooks`, preservando seu nome:
  verifica inventário, instalação limpa, dependências e comandos do pacote.

## Limites da evidência

O fluxo novo do GitHub Actions ainda depende do push e da execução no PR.
Python 3.12 será verificado pela CI; Windows e Linux não foram executados
localmente. A instalação limpa demonstrada é a estrutura Python mínima;
React, Django/PostgreSQL, RAG, OCR e agentes permanecem nas respectivas issues.
Os manifests antigos, sem versões fixadas, são preservados como experimentos,
sem promessa de reprodução de seus resultados nesta tarefa.

## Correspondência com critérios de aceite

| Critério | Evidência |
|---|---|
| Experimentos e fontes preservados com rastreabilidade | Inventário de blobs e verificador, com testes de detecção de alterações |
| Dependências e configuração de exemplo sem segredos | `pyproject.toml`, `.env.example`, `.gitignore` e guia do ambiente |
| Execução em ambiente limpo demonstrada | Instalação em venv novo, `pip check` e comandos do pacote registrados acima |
