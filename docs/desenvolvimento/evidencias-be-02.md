# Evidências locais — BE-02 / #84

Verificação realizada em 18/11/2026, na branch `feat-84-autenticacao-isolamento`,
criada a partir do commit `62c13ea` da BE-01. Este registro não substitui a revisão
e o merge do PR. Todas as usuárias e senhas usadas são fictícias.

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
Found 32 test(s).
Ran 32 tests
OK
```

## Fluxo real por HTTP

Executado com `runserver`, `curl` e o PostgreSQL local. A usuária fictícia foi
removida ao final, e a senha não apareceu no log do servidor.

| Passo | Resultado |
|---|---|
| `GET /api/auth/me` sem sessão | 401 |
| `POST /api/auth/login` sem token CSRF | 403 |
| `POST /api/auth/login` com senha incorreta | 401 |
| `POST /api/auth/login` com credenciais válidas | 200 |
| `GET /api/auth/me` com sessão | 200 |
| `POST /api/auth/logout` sem token CSRF | 403 |
| `POST /api/auth/logout` com token CSRF | 204 |
| `GET /api/auth/me` depois do logout | 401 |

## Sensibilidade dos testes

Cada defeito abaixo foi introduzido em uma cópia descartável do código, e a suíte
falhou em todos os casos.

| Defeito introduzido | Suíte |
|---|---|
| Listagem sem filtro pela dona do registro | Falhou |
| API sem autenticação padrão | Falhou |
| Login sem verificação de CSRF | Falhou |
| Logout sem encerrar a sessão | Falhou |
| Logout público | Falhou |
| `/api/auth/me` público | Falhou |
| Login aceitando qualquer senha | Falhou |
| Comando `criar_usuaria` aceitando senha fraca | Falhou |

## Preservação

`python3 scripts/verificar_legado.py` terminou com
`OK: 70 arquivos históricos preservados no índice e no worktree.`

## Limites da evidência

- Ainda não existem rotas financeiras. O acesso cruzado por ID foi testado com um
  recurso fictício, disponível somente nos testes. As issues BE-03 a BE-06 precisam
  aplicar a mesma base e cobrir o isolamento das próprias rotas.
- O job `backend` da CI e a execução com Python 3.12 dependem do push e do PR.
- Não há limite de tentativas de login, recuperação de senha nem configuração de
  CORS. O frontend precisa usar a mesma origem ou um proxy até que CORS seja definido.

## Correspondência com critérios de aceite

| Critério | Evidência |
|---|---|
| Login e encerramento de sessão funcionam | `LoginTests`, `LogoutTests`, `CsrfTests` e fluxo real por HTTP |
| Consultas e mutações exigem autorização | `ProtecaoDasRotasTests` confere todas as rotas do contrato OpenAPI; `test_sem_sessao_nenhuma_operacao_acessa_ou_modifica_dados` |
| Testes com duas usuárias impedem acesso cruzado por IDs | `IsolamentoEntreUsuariasTests` cobre listagem, consulta, alteração, exclusão e criação com dona forjada |
