# Instalação e configuração do backend

Referência: [BE-01 / #83](https://github.com/anamattos2/grupo11challenge2/issues/83).
Este guia prepara do zero o ambiente local do backend: Docker, PostgreSQL e Django.

Execute os comandos na raiz do repositório, salvo indicação diferente. Os exemplos usam
macOS/Linux. Os equivalentes para o Windows PowerShell estão na
[seção 7](#7-comandos-no-windows-powershell).

## 1. Ferramentas necessárias

| Ferramenta | Versão | Para que serve | Como conferir |
|---|---|---|---|
| Git | Atual | Obter o repositório | `git --version` |
| Python | 3.12 a 3.14 | Executar o Django | `python3 --version` |
| Docker Engine | Atual | Executar o contêiner do PostgreSQL | `docker --version` |
| Docker Compose | V2 | Iniciar os serviços de `infra/compose.yaml` | `docker compose version` |
| PostgreSQL | 17 | Banco de dados | Já vem na imagem `postgres:17-alpine` |

Não é preciso instalar o PostgreSQL no computador quando se usa o Docker.

## 2. Instalar e verificar o Docker

Instale pela documentação oficial do seu sistema:

| Sistema | Instalação |
|---|---|
| macOS | [Docker Desktop para Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |
| Windows | [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/), com WSL 2 |
| Ubuntu | [Docker Engine para Ubuntu](https://docs.docker.com/engine/install/ubuntu/), com o plugin `docker-compose-plugin` |

No Linux, para usar o Docker sem `sudo`, siga os
[passos de pós-instalação](https://docs.docker.com/engine/install/linux-postinstall/).
No macOS e no Windows, abra o Docker Desktop e aguarde ele terminar de iniciar.

Confira a instalação:

```bash
docker --version
docker compose version
docker info --format '{{.ServerVersion}}'
docker run --rm hello-world
```

O último comando deve exibir `Hello from Docker!`. Se `docker info` falhar, o serviço do
Docker não está em execução.

## 3. Configurar as variáveis de ambiente

```bash
cp .env.example .env
```

O arquivo `.env` é ignorado pelo Git e nunca deve ser versionado. Os valores do exemplo
servem para o uso local. Se quiser trocar a chave do Django, gere um valor novo e cole em
`DJANGO_SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Defina `POSTGRES_PASSWORD` antes de iniciar o banco pela primeira vez. A descrição de cada
variável está no [guia do ambiente](ambiente.md#configuração-de-exemplo).

## 4. Iniciar e verificar o PostgreSQL

Valide a configuração e inicie o banco:

```bash
docker compose --env-file .env -f infra/compose.yaml config --quiet
docker compose --env-file .env -f infra/compose.yaml up -d --wait
```

| Item | Configuração |
|---|---|
| Serviço | `postgres` |
| Imagem | `postgres:17-alpine` |
| Banco, usuário e senha | `POSTGRES_DB`, `POSTGRES_USER` e `POSTGRES_PASSWORD` do `.env` |
| Porta | `127.0.0.1:${POSTGRES_PORT}`, acessível somente neste computador |
| Dados | Volume Docker `grupo11_postgres-data` |

Confira se o banco está saudável e aceita conexões:

```bash
docker compose --env-file .env -f infra/compose.yaml ps
docker compose --env-file .env -f infra/compose.yaml exec postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose --env-file .env -f infra/compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version();"'
```

O serviço deve aparecer como `healthy`, e `pg_isready` deve informar `accepting connections`.

Para abrir um terminal SQL:

```bash
docker compose --env-file .env -f infra/compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

### Alternativa sem Docker

Use esta opção somente se não for possível executar o Docker. Instale o
[PostgreSQL 17](https://www.postgresql.org/download/), abra o `psql` com um usuário
administrador e crie o usuário e o banco do projeto:

```sql
CREATE ROLE grupo11 WITH LOGIN PASSWORD 'troque-esta-senha-local' CREATEDB;
CREATE DATABASE grupo11 OWNER grupo11;
```

A permissão `CREATEDB` é necessária porque os testes criam um banco temporário. Os valores
precisam ser iguais aos de `POSTGRES_USER`, `POSTGRES_PASSWORD` e `POSTGRES_DB` no `.env`.
Depois, siga para a seção 5.

## 5. Instalar e inicializar o Django

Crie o ambiente virtual e instale as dependências:

```bash
python3 -m venv .venv-api
.venv-api/bin/python -m pip install -r apps/api/requirements.txt
.venv-api/bin/python -m pip check
```

Confira a configuração e crie as tabelas no banco:

```bash
.venv-api/bin/python apps/api/manage.py check
.venv-api/bin/python apps/api/manage.py migrate
.venv-api/bin/python apps/api/manage.py migrate --check
```

`check` deve informar `System check identified no issues`. `migrate --check` termina sem
mensagens quando não há migrations pendentes. Esta etapa não exige criar um superusuário,
porque o painel administrativo do Django não está instalado.

Inicie o servidor:

```bash
.venv-api/bin/python apps/api/manage.py runserver
```

Em outro terminal, confira a API:

```bash
curl http://127.0.0.1:8000/api/health
```

A resposta esperada é `{"status": "ok", "database": "ok"}`. A documentação interativa fica
em <http://127.0.0.1:8000/api/docs>.

Execute os testes dentro de `apps/api`:

```bash
cd apps/api
../../.venv-api/bin/python manage.py test
```

## 6. Uso diário e problemas comuns

| Ação | Comando |
|---|---|
| Iniciar o banco | `docker compose --env-file .env -f infra/compose.yaml up -d --wait` |
| Ver os logs | `docker compose --env-file .env -f infra/compose.yaml logs postgres` |
| Parar e manter os dados | `docker compose --env-file .env -f infra/compose.yaml down` |
| Apagar os dados locais | `docker compose --env-file .env -f infra/compose.yaml down -v` |
| Aplicar novas migrations | `.venv-api/bin/python apps/api/manage.py migrate` |

O comando `down -v` apaga definitivamente o banco local deste projeto.

| Mensagem | Causa | Solução |
|---|---|---|
| `couldn't find env file` | O `.env` não existe na raiz | Execute `cp .env.example .env` |
| `Cannot connect to the Docker daemon` | O Docker não está em execução | Abra o Docker Desktop ou inicie o serviço do Docker |
| `Bind for 127.0.0.1:5432 failed: port is already allocated` | Outro programa usa a porta | Altere `POSTGRES_PORT` no `.env` e inicie o banco novamente |
| `Connection refused` | O PostgreSQL está parado | Inicie o banco e confira com `ps` |
| `password authentication failed` | A senha do `.env` mudou depois da criação do volume | Volte à senha original ou recrie o banco com `down -v`, o que apaga os dados |
| `Variável de ambiente obrigatória ausente` | Falta uma variável no `.env` | Compare o `.env` com o `.env.example` |
| HTTP 400 ao acessar a API | O endereço não está em `DJANGO_ALLOWED_HOSTS` | Inclua o endereço nessa variável |

## 7. Comandos no Windows PowerShell

Execute o Docker e o PostgreSQL com os mesmos comandos `docker compose` das seções 4 e 6.
Para as demais etapas:

| Etapa | Comando |
|---|---|
| Criar o `.env` | `Copy-Item .env.example .env` |
| Criar o ambiente virtual | `py -3.12 -m venv .venv-api` |
| Instalar as dependências | `.venv-api\Scripts\python.exe -m pip install -r apps\api\requirements.txt` |
| Conferir a configuração | `.venv-api\Scripts\python.exe apps\api\manage.py check` |
| Criar as tabelas | `.venv-api\Scripts\python.exe apps\api\manage.py migrate` |
| Iniciar o servidor | `.venv-api\Scripts\python.exe apps\api\manage.py runserver` |
| Conferir a API | `Invoke-RestMethod http://127.0.0.1:8000/api/health` |
