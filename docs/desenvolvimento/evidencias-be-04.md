# Evidências locais — BE-04 / #86

Verificação realizada em 18/11/2026, na branch `feat-86-receitas-despesas-categorias`,
criada a partir do commit `886cbf7` da BE-03. Este registro não substitui a revisão e
o merge do PR. Todas as usuárias, senhas e valores usados são fictícios.

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
Found 101 test(s).
Ran 101 tests
OK
```

## Migration

A migration `financas.0002_categorias_transacoes` foi aplicada, revertida com
`migrate financas 0001` e aplicada novamente. `migrate --check` terminou sem pendências.

## Fluxo real por HTTP

Executado com `runserver` e duas sessões fictícias no PostgreSQL local. Os dados foram
removidos ao final, a senha não apareceu no log e nenhuma resposta teve status 500.

| Passo | Resultado |
|---|---|
| Ana cria categorias de despesa e receita | 201 |
| Ana cria uma despesa e uma receita | 201 |
| Ana edita a despesa | 200 |
| Valor enviado como número JSON | 422 |
| Tipo da transação diferente do tipo da categoria | 422 |
| Filtro de 01/03/2026 a 31/03/2026 | 200, receitas `3000.00`, despesas `100.10`, resultado `2899.90`, moeda `BRL` |
| Filtro pela categoria de despesa | 200, despesas `100.10` e 1 registro |
| Exclusão de categoria em uso | 409 |
| Escrita sem token CSRF | 403 |
| Bia lista transações | 200, nenhum registro e totais zerados |
| Bia consulta, edita e exclui a transação da Ana por ID | 404 nas três tentativas |
| Bia registra transação na categoria da Ana | 422 |
| Ana confere a transação depois das tentativas | 200, sem alteração |
| Listagem sem sessão | 401 |
| Ana exclui a própria transação | 204 |

## Concorrência

| Cenário | Rodadas | Resultado |
|---|---|---|
| 12 criações simultâneas de categoria com o mesmo nome | 1 | 1 resposta 201, 11 respostas 409 e 1 categoria gravada |
| Excluir categoria enquanto 4 transações são criadas nela | 25 | Nenhuma transação órfã ou resposta inconsistente |
| Mudar o tipo da categoria enquanto 3 transações são criadas nela | 25 | Nenhuma transação com tipo diferente da categoria |
| Excluir transação enquanto 3 edições são enviadas | 25 | Nenhum registro excluído voltou a existir |

## Sensibilidade dos testes

33 defeitos foram introduzidos em cópias descartáveis do código, e a suíte final falhou
em todos os casos. Eles cobrem:

- Acesso a transações, categorias e contas de outra usuária.
- Validação de valor, data, tipo, essencialidade e nomes repetidos.
- Limites do período, filtros, paginação e cálculo dos totais.
- Exclusão e troca de tipo de categoria em uso, e remoção de usuária com registros.
- Restrição de valor positivo no banco, rota pública e contrato divergente do código.

Na primeira execução, a remoção da validação estrita de data não foi detectada. Os
formatos que passavam a ser aceitos foram incluídos nos testes, e o defeito passou a
ser detectado.

## Preservação

`python3 scripts/verificar_legado.py` terminou com
`OK: 70 arquivos históricos preservados no índice e no worktree.`

## Limites da evidência

- O job `backend` da CI e a execução com Python 3.12 dependem do push e do PR.
- Totais por categoria pertencem à BE-06, e o cálculo da reserva, à BE-05.
- Categorias não são criadas automaticamente: a usuária precisa cadastrá-las antes da
  primeira transação.

## Correspondência com critérios de aceite

| Critério | Evidência |
|---|---|
| Valores usam representação decimal e validação | `test_valor_preserva_decimal_exato`, `test_recusa_valor_invalido`, `test_totais_usam_decimal_exato_e_identificam_moeda` e `test_banco_recusa_valor_nao_positivo` |
| CRUD e filtros por período e categoria funcionam | `CategoriaTests`, `TransacaoTests`, `FiltrosTests` e fluxo real por HTTP |
| Isolamento por usuária coberto por testes | `IsolamentoDeTransacoesTests`, `test_nao_acessa_categoria_de_outra_usuaria_por_id` e tentativas da segunda usuária por HTTP |
