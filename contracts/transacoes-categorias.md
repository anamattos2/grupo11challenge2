# Contrato de categorias, receitas e despesas

Referência: [BE-04 / #86](https://github.com/anamattos2/grupo11challenge2/issues/86).
O contrato executável é o [openapi.json](openapi.json). Este guia resume as regras
para quem consome a API.

Receitas e despesas são informadas pela própria usuária. Nada é importado de bancos,
e registrar uma transação não altera o `saldo_declarado` de uma conta.

## Regras gerais

- Todas as rotas exigem sessão. Escritas também exigem o cabeçalho `X-CSRFToken`.
- A dona do registro vem sempre da sessão. Campos como `usuaria_id` são recusados.
- `PUT` substitui o registro inteiro: campo opcional omitido volta ao valor padrão.

## Categorias

| Método e rota | Uso | Sucesso | Erros específicos |
|---|---|---|---|
| `GET /api/categorias` | Lista as próprias categorias | 200 | — |
| `POST /api/categorias` | Cria uma categoria | 201 | 409, 422 |
| `GET /api/categorias/{categoria_id}` | Consulta uma categoria própria | 200 | 404 |
| `PUT /api/categorias/{categoria_id}` | Substitui uma categoria própria | 200 | 404, 409, 422 |
| `DELETE /api/categorias/{categoria_id}` | Exclui uma categoria própria sem transações | 204 | 404, 409 |

| Campo | Obrigatório | Regra |
|---|---|---|
| `nome` | Sim | 1 a 80 caracteres após remover espaços nas pontas, sem caracteres de controle; único por usuária e tipo, sem diferenciar maiúsculas e minúsculas |
| `tipo` | Sim | `receita` ou `despesa`; não muda se houver transações vinculadas |
| `essencial` | Não | `true` ou `false` (padrão); `true` só é aceito em categorias de despesa |

## Transações

| Método e rota | Uso | Sucesso | Erros específicos |
|---|---|---|---|
| `GET /api/transacoes` | Lista com filtros e totais | 200 | 422 |
| `POST /api/transacoes` | Registra uma receita ou despesa | 201 | 422 |
| `GET /api/transacoes/{transacao_id}` | Consulta uma transação própria | 200 | 404 |
| `PUT /api/transacoes/{transacao_id}` | Substitui uma transação própria | 200 | 404, 422 |
| `DELETE /api/transacoes/{transacao_id}` | Exclui uma transação própria | 204 | 404 |

| Campo | Obrigatório | Regra |
|---|---|---|
| `tipo` | Sim | `receita` ou `despesa`; precisa ser igual ao tipo da categoria |
| `valor` | Sim | Texto decimal maior que zero, com ponto, até 12 dígitos inteiros e 2 casas decimais |
| `data` | Sim | Data real no formato `AAAA-MM-DD`, até o dia atual no fuso `America/Sao_Paulo` |
| `categoria_id` | Sim | Número inteiro de uma categoria própria |
| `conta_id` | Não | Número inteiro de uma conta própria, ou `null` |
| `descricao` | Não | Até 200 caracteres, sem caracteres de controle; padrão vazio |

O valor é enviado como texto para não perder precisão: `"89.90"` é aceito, enquanto
`89.90`, `"89,90"`, `"0.00"`, `"-1.00"` e `"1e3"` são recusados. `moeda` é definida
pelo servidor como `BRL` e não pode ser enviada.

Categoria ou conta de outra usuária responde 422 com a mesma mensagem de um ID
inexistente.

## Filtros da listagem

| Parâmetro | Padrão | Regra |
|---|---|---|
| `data_inicio` | Sem limite | `AAAA-MM-DD`, data incluída no resultado |
| `data_fim` | Sem limite | `AAAA-MM-DD`, data incluída; não pode ser anterior a `data_inicio` |
| `categoria_id` | Todas | Número inteiro; categoria de outra usuária retorna lista vazia |
| `tipo` | Ambos | `receita` ou `despesa` |
| `limite` | 50 | 1 a 200 itens por página |
| `deslocamento` | 0 | 0 a 1.000.000 itens ignorados |

Parâmetro desconhecido responde 422. Os itens vêm da data mais recente para a mais
antiga. `totais` e `quantidade` consideram todos os registros do filtro, não só a página.

- **Formato dos totais:** texto decimal com sinal, até 18 dígitos inteiros e sempre 2
  casas (`^-?[0-9]{1,18}\.[0-9]{2}$`). É um formato próprio, maior que o de um valor
  individual, porque a soma de valores válidos passa de 12 dígitos.
- **Consistência:** itens, `totais` e `quantidade` refletem o mesmo estado do banco, inclusive
  quando a página vem vazia. A listagem roda numa transação `REPEATABLE READ`: uma
  transação gravada ao mesmo tempo aparece em todos eles ou em nenhum.

```http
GET /api/transacoes?data_inicio=2026-03-01&data_fim=2026-03-31&limite=1
```

```json
{
  "periodo": {"inicio": "2026-03-01", "fim": "2026-03-31"},
  "moeda": "BRL",
  "totais": {"receitas": "3000.00", "despesas": "100.10", "resultado": "2899.90"},
  "quantidade": 2,
  "limite": 1,
  "deslocamento": 0,
  "itens": [
    {
      "id": 1,
      "tipo": "despesa",
      "valor": "100.10",
      "moeda": "BRL",
      "data": "2026-03-11",
      "descricao": "Feira",
      "categoria_id": 1,
      "categoria_nome": "Mercado",
      "conta_id": null,
      "criado_em": "2026-11-18T14:33:46.358Z",
      "atualizado_em": "2026-11-18T14:33:46.358Z"
    }
  ]
}
```

## Erros

| Status | Quando | Corpo |
|---|---|---|
| 401 | Sem sessão válida | `{"detail": "Unauthorized"}` |
| 403 | Escrita sem token CSRF válido | `{"detail": "CSRF check Failed"}` |
| 404 | Registro inexistente ou de outra usuária, sem distinção | `{"detail": "..."}` |
| 409 | Nome de categoria repetido no mesmo tipo, ou categoria em uso ao excluir ou trocar o tipo. Outros erros de integridade não viram 409 | `{"detail": "..."}` |
| 422 | Dados ou filtros inválidos | `{"detail": [{"type": "...", "loc": ["body", "dados", "campo"], "msg": "..."}]}` |

No 422, use o último item de `loc` para associar o erro ao campo e `type` para escolher
a mensagem exibida. O texto de `msg` pode vir em inglês.
