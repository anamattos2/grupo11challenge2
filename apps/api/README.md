# Backend financeiro

Servidor Django / Django Ninja com persistência em PostgreSQL, inicializado na
[BE-01 / #83](https://github.com/anamattos2/grupo11challenge2/issues/83). A
[BE-02 / #84](https://github.com/anamattos2/grupo11challenge2/issues/84) adiciona
sessão e isolamento por usuária, e a
[BE-03 / #85](https://github.com/anamattos2/grupo11challenge2/issues/85), perfil
financeiro e contas manuais. A
[BE-04 / #86](https://github.com/anamattos2/grupo11challenge2/issues/86) adiciona
categorias, receitas e despesas, e a
[BE-05 / #87](https://github.com/anamattos2/grupo11challenge2/issues/87), a reserva
de emergência. A [BE-06 / #88](https://github.com/anamattos2/grupo11challenge2/issues/88)
adiciona as consultas de leitura para as telas e os agentes de IA.

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

## Autenticação

A autenticação é interna ao aplicativo, usa a sessão do Django em cookie e não
envolve login bancário. Não há cadastro público nesta etapa. Crie uma usuária
com dados fictícios pelo terminal, em `apps/api`:

```bash
../../.venv-api/bin/python manage.py criar_usuaria ana.ficticia
```

| Rota | Acesso | Resultado |
|---|---|---|
| `GET /api/auth/csrf` | Pública | 200 com o token CSRF e o cookie `csrftoken` |
| `POST /api/auth/login` | Pública, com CSRF | 200 com a usuária; 401 para credenciais inválidas |
| `GET /api/auth/me` | Sessão | 200 com a usuária atual |
| `POST /api/auth/logout` | Sessão, com CSRF | 204 e sessão apagada no servidor |

Requisições de escrita enviam o token no cabeçalho `X-CSRFToken`. O login renova
o token, portanto leia novamente o cookie `csrftoken` depois de entrar. Sem sessão,
as rotas protegidas respondem 401; sem token CSRF, as escritas respondem 403. A
sessão expira em 8 horas.

### Regras para novas rotas

- Toda rota exige sessão por padrão. Uma rota pública precisa de `auth=None` e de
  inclusão explícita na lista verificada em `tests/test_autenticacao.py`.
- Modelos com dados pessoais herdam de `RegistroDaUsuaria`.
- Listagens usam `Modelo.objects.da_usuaria(request.auth)`.
- Consultas e mutações por ID usam `obter_da_usuaria_ou_404`. O registro de outra
  usuária responde 404, igual a um ID inexistente.
- A dona do registro vem de `request.auth`, nunca do corpo ou da URL.

## Perfil e contas manuais

Perfis, nomes e saldos são declarados pela usuária e não são sincronizados com
bancos. Rotas, validações e erros estão em
[contracts/perfil-contas.md](../../contracts/perfil-contas.md).

## Categorias, receitas e despesas

Transações são informadas pela usuária, nunca importadas de bancos, e não alteram o
saldo declarado das contas. Rotas, validações, filtros e totais estão em
[contracts/transacoes-categorias.md](../../contracts/transacoes-categorias.md).

## Reserva de emergência

`GET /api/reserva` calcula meta, saldo declarado e progresso a partir dos valores
cadastrados no aplicativo. Os filtros `mes_inicio` e `mes_fim` definem o período das
despesas essenciais; sem eles, a API usa os 3 últimos meses completos. Regras, decisões
e erros estão em [contracts/reserva.md](../../contracts/reserva.md).

## Consultas financeiras

As rotas em `/api/consultas` são somente de leitura e atendem as telas e os agentes de IA.
Agentes usam apenas as ferramentas permitidas, com parâmetros tipados, e a usuária vem
sempre da sessão. Ferramentas, resultados e erros estão em
[contracts/consultas-financeiras.md](../../contracts/consultas-financeiras.md).

## Contrato OpenAPI

Ao alterar uma rota ou schema, atualize o contrato versionado em `apps/api`:

```bash
../../.venv-api/bin/python manage.py exportar_contrato
```

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
