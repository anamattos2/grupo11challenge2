# Backend financeiro

Servidor Django / Django Ninja com persistência em PostgreSQL, inicializado na
[BE-01 / #83](https://github.com/anamattos2/grupo11challenge2/issues/83). Esta
etapa entrega a base executável: configuração, conexão, migrations nativas do
Django e verificação de saúde. Modelos financeiros, autenticação e endpoints de
negócio pertencem às respectivas issues.

Responsabilidades: sessão, autorização, regras financeiras, persistência e
ferramentas determinísticas para os agentes. OpenAPI é a referência das
interfaces HTTP. Nunca aceitar identidade sugerida pelo modelo como autorização.

## Executar localmente

Pré-requisitos: Python 3.12 a 3.14 e Docker com Compose. Na raiz do repositório:

```bash
cp .env.example .env
python3 -m venv .venv-api
.venv-api/bin/python -m pip install -r apps/api/requirements.txt
docker compose --env-file .env -f infra/compose.yaml up -d --wait
.venv-api/bin/python apps/api/manage.py migrate
.venv-api/bin/python apps/api/manage.py runserver
```

| Endereço | Conteúdo |
|---|---|
| <http://127.0.0.1:8000/api/health> | Estado da API e da conexão com o banco |
| <http://127.0.0.1:8000/api/docs> | Documentação interativa |
| <http://127.0.0.1:8000/api/openapi.json> | Contrato OpenAPI |

`/api/health` responde 200 com o banco acessível e 503 quando ele está
indisponível. A página `/api/docs` carrega seus recursos visuais de uma CDN.

## Testar

Execute os testes dentro de `apps/api`, pois a raiz tem outra pasta `tests`:

```bash
cd apps/api
../../.venv-api/bin/python manage.py test
```

## Configuração

Toda a configuração vem de variáveis de ambiente, descritas no
[guia do ambiente](../../docs/desenvolvimento/ambiente.md). A aplicação não
inicia se `DJANGO_SECRET_KEY`, `POSTGRES_DB`, `POSTGRES_USER` ou
`POSTGRES_PASSWORD` estiverem ausentes.
