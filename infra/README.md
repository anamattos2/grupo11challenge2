# Execução e implantação

O [guia local](../docs/desenvolvimento/ambiente.md) documenta a instalação.

`compose.yaml` inicia o PostgreSQL local usado pelo
[backend](../apps/api/README.md). A porta fica acessível somente em `127.0.0.1`.
Execute os comandos na raiz do repositório, depois de criar o `.env`:

```bash
docker compose --env-file .env -f infra/compose.yaml up -d --wait
docker compose --env-file .env -f infra/compose.yaml down
```

Para recomeçar com um banco vazio, use `down -v`. Esse comando apaga
definitivamente os dados locais do volume deste projeto.

Frontend e serviços de modelos serão adicionados nas respectivas issues.
Credenciais reais ficam em variáveis de ambiente ou em arquivos locais ignorados.
