# Evidências locais — BE-01 / #83

Verificação realizada em 18/11/2026, na branch `feat-83-backend-django-postgres`,
a partir do commit `28ff0ef` da `main`. Este registro não substitui a revisão e
o merge do PR. Todos os valores de configuração usados são fictícios.

## Ambiente

macOS (Apple Silicon), Python 3.14.7, Docker Compose 5.7.0 e PostgreSQL 17.12
(`postgres:17-alpine`). Dependências instaladas em ambiente virtual novo, a partir
de `apps/api/requirements.txt`; `pip check` não encontrou conflitos.

## Migrations em ambiente limpo

O volume local foi removido antes da execução, e o banco iniciou sem tabelas.

```text
docker compose --env-file .env -f infra/compose.yaml down -v
Volume grupo11_postgres-data Removed

docker compose --env-file .env -f infra/compose.yaml up -d --wait
Container grupo11-postgres-1 Healthy

Tabelas no schema public antes do migrate: 0

.venv-api/bin/python apps/api/manage.py migrate --noinput
Applying sessions.0001_initial... OK

.venv-api/bin/python apps/api/manage.py migrate --check
código de saída 0

Migrations aplicadas: 15; pendentes: 0
Tabelas no schema public depois do migrate: 9
```

`makemigrations --check --dry-run` informou `No changes detected`.

## API e conexão com o PostgreSQL

```text
GET /api/health
HTTP 200 {"status": "ok", "database": "ok"}

GET /api/docs
HTTP 200

GET /api/openapi.json
HTTP 200
```

Com o contêiner parado, `/api/health` respondeu HTTP 503 com
`{"status": "indisponivel", "database": "erro"}`. Ao religar o banco, voltou a
responder HTTP 200 sem reiniciar a API.

## Testes

```text
cd apps/api
../../.venv-api/bin/python manage.py test
Found 5 test(s).
Ran 5 tests
OK
```

## Configuração sem credenciais versionadas

- Nenhum arquivo `.env` está versionado; `.env` e `.venv-api/` são ignorados.
- `.env.example`, `infra/compose.yaml` e a CI contêm apenas valores fictícios.
- Sem uma variável obrigatória, a aplicação não inicia:

```text
DJANGO_SECRET_KEY= manage.py check
ImproperlyConfigured: Variável de ambiente obrigatória ausente: DJANGO_SECRET_KEY

POSTGRES_PASSWORD= manage.py check
ImproperlyConfigured: Variável de ambiente obrigatória ausente: POSTGRES_PASSWORD
```

## Preservação

`python3 scripts/verificar_legado.py` terminou com
`OK: 70 arquivos históricos preservados no índice e no worktree.`

## Limites da evidência

O job `backend` da CI e a execução com Python 3.12 dependem do push e do PR.
Linux e Windows não foram executados localmente. Modelos financeiros,
autenticação e endpoints de negócio estão fora do escopo desta issue.

## Correspondência com critérios de aceite

| Critério | Evidência |
|---|---|
| API inicia e conecta ao PostgreSQL | `/api/health` responde 200 com `"database": "ok"` |
| Migrations executam em ambiente limpo | 15 migrations aplicadas em banco sem tabelas, com `migrate --check` sem pendências |
| Configuração usa variáveis de ambiente sem credenciais versionadas | `.env` ignorado, exemplos fictícios e recusa de inicialização sem variável obrigatória |
