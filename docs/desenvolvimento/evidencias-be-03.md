# Evidências locais — BE-03 / #85

Verificação realizada em 18/11/2026, na branch `feat-85-perfil-contas-manuais`,
criada a partir do commit `7d5dc43` da BE-02. Este registro não substitui a revisão
e o merge do PR. Todas as usuárias, senhas e valores usados são fictícios.

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
Found 56 test(s).
Ran 56 tests
OK
```

## Migration

A migration `financas.0001_initial` foi aplicada, revertida com
`migrate financas zero` e aplicada novamente. `migrate --check` terminou sem
pendências.

## Fluxo real por HTTP

Executado com `runserver` e duas sessões fictícias no PostgreSQL local. Os dados foram
removidos ao final, a senha não apareceu no log e nenhuma resposta teve status 500.

| Passo | Resultado |
|---|---|
| Ana consulta perfil ainda não criado | 404 |
| Ana cria o perfil | 201 |
| Ana edita o perfil | 200 |
| Ana cria conta com saldo `"1500.50"` | 201 |
| Ana edita nome, tipo e saldo da conta | 200 |
| Saldo enviado como número JSON | 422 |
| Nome repetido com outra caixa | 409 |
| Escrita sem token CSRF | 403 |
| Bia lista contas | 200, lista vazia |
| Bia consulta a conta da Ana por ID | 404 |
| Bia edita a conta da Ana por ID | 404 |
| Ana confere a conta depois da tentativa | 200, sem alteração |
| Listagem sem sessão | 401 |
| 12 criações simultâneas com o mesmo nome | 1 resposta 201, 11 respostas 409 e 1 conta gravada |
| 8 gravações simultâneas do primeiro perfil | 1 resposta 201, 7 respostas 200 e 1 perfil gravado |

## Sensibilidade dos testes

Cada defeito abaixo foi introduzido em uma cópia descartável do código, e a suíte
falhou em todos os casos.

| Defeito introduzido | Suíte |
|---|---|
| Listagem de contas sem filtro pela dona | Falhou |
| Consulta de conta sem filtro pela dona | Falhou |
| Edição de conta sem filtro pela dona | Falhou |
| Perfil lido de qualquer usuária | Falhou |
| Conta criada para outra usuária | Falhou |
| Saldo aceitando número JSON | Falhou |
| Saldo sem normalizar as casas decimais | Falhou |
| Campos extras ignorados | Falhou |
| Texto aceitando caracteres de controle | Falhou |
| Nome duplicado gerando erro 500 | Falhou |
| Nome único diferenciando maiúsculas e minúsculas | Falhou |
| Rota de contas pública | Falhou |
| Contrato divergente do código | Falhou |

## Limites da evidência

- O job `backend` da CI e a execução com Python 3.12 dependem do push e do PR.
- Esta entrega não inclui exclusão de contas, que depende das regras de transações
  da BE-04.
- As regras da reserva, como saldo inicial, aportes e retiradas, pertencem à BE-05.

## Correspondência com critérios de aceite

| Critério | Evidência |
|---|---|
| Criação e edição autenticadas disponíveis | `PerfilTests`, `ContaTests`, `test_sem_sessao_nenhuma_operacao_acessa_ou_modifica_contas` e fluxo real por HTTP |
| Contas pertencem à usuária autorizada | `IsolamentoDeContasTests`, `test_cria_conta_para_a_usuaria_autenticada` e tentativas da segunda usuária por HTTP |
| Validações e contratos documentados | `contracts/perfil-contas.md`, `contracts/openapi.json` e `ContratoTests` |
