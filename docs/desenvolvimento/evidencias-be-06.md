# Evidências locais — BE-06 / #88

Verificação realizada em 18/11/2026, na branch `feat-88-consultas-financeiras-ferramentas`,
criada a partir do commit `a344c59` da BE-05. Este registro não substitui a revisão e o
merge do PR. Todas as usuárias, senhas e valores usados são fictícios.

## Ambiente

macOS, Python 3.14.7, Django 5.2.19, Django Ninja 1.8.0 e PostgreSQL
(`postgres:17-alpine`), iniciado por `infra/compose.yaml`.

## Testes automatizados

```text
cd apps/api
../../.venv-api/bin/python manage.py check
System check identified no issues (0 silenced).

../../.venv-api/bin/python manage.py makemigrations --check --dry-run
No changes detected

../../.venv-api/bin/python manage.py test
Found 198 test(s).
Ran 198 tests
OK
```

A suíte também passou em Python 3.12.16, a versão usada pela CI, em contêiner com
PostgreSQL 17 limpo. O contrato OpenAPI gerado foi igual nas duas versões.

## Fluxo real por HTTP

Executado com `runserver` e duas sessões fictícias no PostgreSQL local. Os dados foram
removidos ao final, a senha não apareceu no log e nenhuma resposta teve status 500.

| Passo | Resultado |
|---|---|
| Totais por categoria em outubro de 2026 | 200, receitas `3000.00` e despesas `2000.00`, com período e moeda |
| Repetição da mesma consulta | Mesmo `evidencia_id` |
| Resumo do período | 200, despesas essenciais `2000.00` e resultado `1000.00` |
| Reserva | 200, meta `6000.00`, saldo `600.00`, `meses_cobertos` `0.30` e progresso `10.00` |
| Saldos das contas | 200, total declarado `150.10` |
| Catálogo | 200, com as 4 ferramentas permitidas |
| Segunda usuária consulta o mesmo período | 200, totais zerados |
| `usuaria_id` na URL | 422 |
| `sql` na URL | 422 |
| SQL no campo de data | 422 |
| `POST` em rota de consulta | 405 |
| Consulta sem sessão | 401 |

## Controles das ferramentas

| Controle | Teste |
|---|---|
| Só executa ferramentas da lista | `test_recusa_ferramenta_fora_da_lista` |
| Recusa identidade e SQL nos parâmetros | `test_recusa_identidade_ou_sql_nos_parametros_de_toda_ferramenta` |
| Recusa SQL em campos tipados | `test_recusa_sql_nos_campos_tipados` |
| Exige usuária autenticada | `test_exige_usuaria_autenticada` |
| Toda consulta ao banco é `SELECT` filtrado pela usuária | `test_toda_consulta_e_leitura_filtrada_pela_usuaria` |
| Rotas publicadas somente com `GET` | `test_contrato_publica_somente_leitura` |
| Erro não devolve o valor recebido | `test_erro_nao_devolve_o_valor_recebido` |

## Sensibilidade dos testes

41 defeitos foram introduzidos em cópias descartáveis do código, e a suíte final falhou em
todos os casos. Eles cobrem totais, filtros, cobertura, identificação das evidências,
autenticação, isolamento, lista de ferramentas e contrato.

Na primeira execução, dois defeitos no cálculo do `evidencia_id` não foram detectados. Os
testes foram reforçados para variar parâmetros e ferramenta com dados iguais.

## Preservação

`python3 scripts/verificar_legado.py` terminou com
`OK: 70 arquivos históricos preservados no índice e no worktree.`

## Limites da evidência

- A dependência S4-01 (#75) continua aberta. Este contrato segue a interface
  “IA → ferramenta financeira” da arquitetura e deve ser conferido quando ela for concluída.
- Os agentes ainda não existem. Os controles foram testados diretamente nas ferramentas, e
  a conexão com os assistentes pertence à S6-01 (#99).
- O resultado do job `backend` da CI depende do push e do PR.

## Correspondência com critérios de aceite

| Critério | Evidência |
|---|---|
| Totais por categoria e período calculados com os registros locais | `TotaisPorCategoriaTests`, `ResumoEContasTests` e fluxo real por HTTP |
| Meta, saldo e cobertura possuem contrato explícito | `contracts/consultas-financeiras.md`, `contracts/openapi.json` e `ReservaTests` |
| Agentes não executam SQL livre nem acessam dados de outra usuária | `SegurancaDasFerramentasTests` e `RotasDeConsultaTests` |
