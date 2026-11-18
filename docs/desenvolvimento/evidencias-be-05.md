# Evidências locais — BE-05 / #87

Verificação realizada em 18/11/2026, na branch `feat-87-regras-movimentacoes-reserva`,
criada a partir do commit `08860b5` da BE-04. Este registro não substitui a revisão e o
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
Found 157 test(s).
Ran 157 tests
OK
```

A suíte também passou em Python 3.12.16, a versão usada pela CI, em contêiner com
PostgreSQL 17 limpo. O contrato OpenAPI gerado foi igual nas duas versões.

## Migration

A migration `financas.0003_reserva_emergencia` foi aplicada, revertida com
`migrate financas 0002` e aplicada novamente. `migrate --check` terminou sem pendências.

## Casos determinísticos

| Caso | Entrada | Resultado |
|---|---|---|
| Meta | R$ 2.000,00 × 3 meses | R$ 6.000,00 |
| Saldo | R$ 500,00 + R$ 200,00 − R$ 100,00 | R$ 600,00 |
| Progresso | R$ 600,00 ÷ R$ 6.000,00 | 10,00% |
| Meta zero | Meta de R$ 0,00 | Estado `meta_zero`, sem progresso |
| Dados ausentes | Sem despesas, cobertura ou saldo inicial | Estado `dados_insuficientes` e lista do que falta |
| Arredondamento | 10,125 | 10,13 |
| Média | R$ 200,01 em 3 meses | R$ 66,67 |

## Fluxo real por HTTP

Executado com `runserver` e sessões fictícias no PostgreSQL local. Os dados foram
removidos ao final, a senha não apareceu no log e nenhuma resposta teve status 500.

| Passo | Resultado |
|---|---|
| Resumo sem dados | 200, `dados_insuficientes` e os três itens em `faltando` |
| Movimentação sem reserva configurada | 409 |
| Configuração da reserva | 201 |
| Aporte de R$ 200,00 e retirada de R$ 100,00 | 201 |
| `GET /api/reserva?mes_inicio=2026-10&mes_fim=2026-10` | 200, meta `6000.00`, saldo `600.00` e progresso `10.00` |
| Resumo sem filtros | 200, período de `2026-08` a `2026-10` |
| Retirada acima do saldo | 409 |
| Filtro com o mês atual, ainda incompleto | 422 |
| Cobertura de 61 meses | 422 |
| Escrita sem token CSRF | 403 |
| Segunda usuária consulta o resumo | 200, sem dados da primeira |
| Segunda usuária consulta e exclui movimentação da primeira por ID | 404 nas duas tentativas |
| Consulta sem sessão | 401 |

## Concorrência

| Cenário | Rodadas | Resultado |
|---|---|---|
| 8 gravações simultâneas da primeira reserva | 1 | 1 resposta 201, 7 respostas 200 e 1 reserva gravada |
| 10 retiradas simultâneas de R$ 100,00 com saldo de R$ 500,00 | 1 | 5 respostas 201, 5 respostas 409 e saldo final `0.00` |
| Retiradas, exclusão de aporte e edição do saldo inicial ao mesmo tempo | 25 | Nenhuma rodada terminou com saldo negativo |

## Sensibilidade dos testes

48 defeitos foram introduzidos em cópias descartáveis do código, e a suíte falhou em
todos os casos. Eles cobrem:

- Fórmulas de meta, saldo, progresso, média e arredondamento.
- Meta zero, dados ausentes, limites do período e meses sem registro.
- Retiradas, exclusão de aportes e redução do saldo inicial acima do permitido.
- Acesso a dados de outra usuária e restrições do banco.
- Rota pública e contrato divergente do código.

## Preservação

`python3 scripts/verificar_legado.py` terminou com
`OK: 70 arquivos históricos preservados no índice e no worktree.`

## Limites da evidência

- O resultado do job `backend` da CI depende do push e do PR.
- O saldo é validado pelo total atual, sem reconstruir a ordem das datas informadas.
- Movimentações não são editadas: a correção é feita por exclusão e novo registro.
- Com as validações atuais, a API não produz meta zero a partir de despesas registradas.
  Esse estado é coberto pelos testes das regras de cálculo.

## Correspondência com critérios de aceite

| Critério | Evidência |
|---|---|
| Meta usa despesas essenciais mensais vezes meses de cobertura | `test_meta_multiplica_despesas_mensais_por_meses_de_cobertura`, `test_calcula_o_exemplo_de_referencia` e `test_considera_somente_despesas_essenciais_da_usuaria` |
| Saldo usa saldo inicial mais aportes confirmados menos retiradas confirmadas | `test_saldo_soma_aportes_e_subtrai_retiradas`, `MovimentacaoTests` e fluxo real por HTTP |
| Progresso trata meta zero e cálculos possuem testes determinísticos | `CalculosTests`, em especial `test_progresso_nao_e_calculado_com_meta_zero` e `test_avalia_meta_zero_sem_dividir_por_zero` |
