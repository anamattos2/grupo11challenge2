# Contrato de perfil financeiro e contas manuais

Referência: [BE-03 / #85](https://github.com/anamattos2/grupo11challenge2/issues/85).
O contrato executável é o [openapi.json](openapi.json). Este guia resume as regras
para quem consome a API.

Perfis, nomes e saldos são declarados pela própria usuária. Não há conexão ou
sincronização com bancos, e `saldo_declarado` não é um saldo bancário verificado.

## Regras gerais

- Todas as rotas exigem sessão. Escritas também exigem o cabeçalho `X-CSRFToken`.
- A dona do registro vem sempre da sessão. Campos como `usuaria_id` são recusados.
- Corpo e respostas usam JSON.

## Rotas

| Método e rota | Uso | Sucesso | Erros específicos |
|---|---|---|---|
| `GET /api/perfil` | Consulta o próprio perfil | 200 | 404 se ainda não existir |
| `PUT /api/perfil` | Cria ou substitui o próprio perfil | 201 ao criar, 200 ao editar | 422 |
| `GET /api/contas` | Lista as próprias contas, por ordem de criação | 200 | — |
| `POST /api/contas` | Cria uma conta | 201 | 409, 422 |
| `GET /api/contas/{conta_id}` | Consulta uma conta própria | 200 | 404 |
| `PUT /api/contas/{conta_id}` | Substitui nome, tipo e saldo de uma conta própria | 200 | 404, 409, 422 |

A API não oferece exclusão de contas. Transações podem ser vinculadas a uma conta,
conforme [transacoes-categorias.md](transacoes-categorias.md), sem alterar o saldo
declarado.

## Validações

### Perfil

| Campo | Obrigatório | Regra |
|---|---|---|
| `nome_exibicao` | Sim | 1 a 80 caracteres após remover espaços nas pontas, sem caracteres de controle |
| `previsibilidade_renda` | Não | `fixa`, `variavel`, `mista` ou `nao_informada` (padrão) |

### Conta manual

| Campo | Obrigatório | Regra |
|---|---|---|
| `nome` | Sim | Mesma regra de `nome_exibicao`; único por usuária, sem diferenciar maiúsculas e minúsculas |
| `tipo` | Sim | `corrente`, `poupanca`, `carteira`, `reserva` ou `outra` |
| `saldo_declarado` | Sim | Texto decimal com ponto, até 12 dígitos inteiros e 2 casas decimais; pode ser negativo |

O saldo é enviado como texto para não perder precisão: `"1500.50"` é aceito, enquanto
`1500.50`, `"1500,50"`, `"1.234"` e `"1e3"` são recusados. A resposta sempre traz duas
casas decimais. `moeda` é definida pelo servidor como `BRL` e não pode ser enviada.

## Exemplo

```http
POST /api/contas
Content-Type: application/json
X-CSRFToken: <token>

{"nome": "Reserva", "tipo": "reserva", "saldo_declarado": "600.00"}
```

```json
{
  "id": 1,
  "nome": "Reserva",
  "tipo": "reserva",
  "saldo_declarado": "600.00",
  "moeda": "BRL",
  "criado_em": "2026-11-18T14:11:32.821Z",
  "atualizado_em": "2026-11-18T14:11:32.821Z"
}
```

## Erros

| Status | Quando | Corpo |
|---|---|---|
| 401 | Sem sessão válida | `{"detail": "Unauthorized"}` |
| 403 | Escrita sem token CSRF válido | `{"detail": "CSRF check Failed"}` |
| 404 | Registro inexistente ou de outra usuária, sem distinção | `{"detail": "..."}` |
| 409 | Nome de conta já usado pela usuária | `{"detail": "Já existe uma conta com este nome."}` |
| 422 | Dados inválidos | `{"detail": [{"type": "...", "loc": ["body", "dados", "campo"], "msg": "..."}]}` |

No 422, use o último item de `loc` para associar o erro ao campo e `type` para escolher
a mensagem exibida. O texto de `msg` pode vir em inglês.

## Manter o contrato atualizado

Depois de alterar uma rota ou schema, execute em `apps/api`:

```bash
../../.venv-api/bin/python manage.py exportar_contrato
```

A suíte do backend falha se `openapi.json` estiver diferente do código.
