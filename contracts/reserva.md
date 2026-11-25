# Contrato da reserva de emergência

Referência: [BE-05 / #87](https://github.com/anamattos2/grupo11challenge2/issues/87).
O contrato executável é o [openapi.json](openapi.json). Este guia resume as regras
para quem consome a API.

A reserva é calculada com valores cadastrados no aplicativo. Os números são declarados
pela usuária e não representam consulta a um saldo bancário.

## Regras de cálculo

| Resultado | Regra |
|---|---|
| Despesas essenciais mensais | Total das despesas em categorias essenciais no período ÷ meses do período com registro |
| Meta | Despesas essenciais mensais × meses de cobertura |
| Saldo declarado | Saldo inicial + aportes − retiradas |
| Progresso | 100 × saldo declarado ÷ meta, somente quando a meta é maior que zero |
| Meses cobertos | Saldo declarado ÷ despesas essenciais mensais, quando esses dados existem |

Exemplo fictício: despesas essenciais de R$ 2.000,00 por mês e 3 meses de cobertura
geram meta de R$ 6.000,00. Saldo inicial de R$ 500,00, aporte de R$ 200,00 e retirada de
R$ 100,00 geram saldo de R$ 600,00 e progresso de 10,00%.

## Decisões adotadas

Estas regras resolvem a pendência P05 da [arquitetura](../docs/arquitetura/arquitetura-inicial.md).

| Tema | Decisão |
|---|---|
| Período-base | Informado pelos filtros `mes_inicio` e `mes_fim`; sem filtros, os 3 últimos meses completos |
| Mês sem registro | Não conta como zero e fica fora da média |
| Mês atual | Não pode ser usado, porque ainda está incompleto |
| Arredondamento | Duas casas decimais, com a metade para cima; a média é arredondada antes de calcular a meta |
| Meses de cobertura | Número inteiro de 1 a 60 |
| Retirada acima do saldo | Recusada, e o saldo declarado nunca fica negativo |
| Moeda | `BRL` |
| Confirmação | Registrar o aporte ou a retirada pela API é a confirmação da usuária |

O progresso pode passar de 100% quando o saldo declarado supera a meta.

## Regras gerais

- Todas as rotas exigem sessão. Escritas também exigem o cabeçalho `X-CSRFToken`.
- A dona do registro vem sempre da sessão. Campos como `usuaria_id` são recusados.

## Rotas

| Método e rota | Uso | Sucesso | Erros específicos |
|---|---|---|---|
| `GET /api/reserva` | Calcula meta, saldo e progresso | 200 | 422 |
| `PUT /api/reserva` | Cria ou substitui saldo inicial e cobertura | 201 ao criar, 200 ao editar | 409, 422 |
| `GET /api/reserva/movimentacoes` | Lista aportes e retiradas | 200 | 422 |
| `POST /api/reserva/movimentacoes` | Registra um aporte ou uma retirada | 201 | 409, 422 |
| `GET /api/reserva/movimentacoes/{movimentacao_id}` | Consulta uma movimentação própria | 200 | 404 |
| `DELETE /api/reserva/movimentacoes/{movimentacao_id}` | Exclui uma movimentação própria | 204 | 404, 409 |

Movimentações não são editadas. Para corrigir um registro, exclua-o e registre outro.

## Consultar a reserva

| Filtro | Padrão | Regra |
|---|---|---|
| `mes_inicio` | Terceiro mês completo anterior ao atual | `AAAA-MM`; deve ser enviado junto com `mes_fim` |
| `mes_fim` | Último mês completo | `AAAA-MM`; anterior ao mês atual e não anterior a `mes_inicio` |

O período pode ter no máximo 24 meses. Filtro desconhecido responde 422.

```http
GET /api/reserva?mes_inicio=2026-10&mes_fim=2026-10
```

```json
{
  "estado": "calculado",
  "faltando": [],
  "moeda": "BRL",
  "periodo": {
    "mes_inicio": "2026-10",
    "mes_fim": "2026-10",
    "meses_no_periodo": 1,
    "meses_com_registro": 1
  },
  "despesas_essenciais_total": "2000.00",
  "despesas_essenciais_mensais": "2000.00",
  "meses_cobertura": 3,
  "meses_cobertos": "0.30",
  "saldo_inicial": "500.00",
  "aportes": "200.00",
  "retiradas": "100.00",
  "saldo_declarado": "600.00",
  "meta": "6000.00",
  "progresso_percentual": "10.00"
}
```

| `estado` | Quando | Campos sem valor |
|---|---|---|
| `calculado` | Todos os dados existem e a meta é maior que zero | Nenhum |
| `meta_zero` | A meta calculada é zero | `progresso_percentual` |
| `dados_insuficientes` | Falta alguma informação listada em `faltando` | `progresso_percentual` e os resultados que dependem do dado ausente |

`faltando` pode conter `despesas_essenciais`, `meses_cobertura` e `saldo_inicial`.

### Formato dos valores do resumo

Todos são texto decimal com 2 casas. O saldo inicial segue o formato do valor
informado (até 12 dígitos inteiros). Os valores calculados acumulam registros e
precisam de formatos maiores:

| Campos | Formato |
|---|---|
| `despesas_essenciais_total`, `despesas_essenciais_mensais`, `aportes`, `retiradas`, `saldo_declarado`, `meta` | `^-?[0-9]{1,20}\.[0-9]{2}$`: somas de muitos registros, e a meta multiplica a média por até 60 meses |
| `progresso_percentual` | `^-?[0-9]{1,23}\.[0-9]{2}$`: passa de 100 quando o saldo supera a meta |

### Consistência

O resumo lê despesas, configuração e movimentações numa única transação
`REPEATABLE READ`, assim como a listagem de movimentações lê a quantidade e os
itens. Uma alteração concorrente, como um saldo inicial novo e uma retirada
registrada logo depois, aparece inteira ou não aparece, e o saldo nunca combina
estados diferentes.

## Validações

### Configuração da reserva

| Campo | Obrigatório | Regra |
|---|---|---|
| `saldo_inicial` | Sim | Texto decimal maior ou igual a zero, com ponto, até 12 dígitos inteiros e 2 casas decimais |
| `meses_cobertura` | Não | Número inteiro de 1 a 60, ou `null`; omitir o campo limpa o valor salvo |

### Movimentação

| Campo | Obrigatório | Regra |
|---|---|---|
| `tipo` | Sim | `aporte` ou `retirada` |
| `valor` | Sim | Texto decimal maior que zero, com ponto, até 12 dígitos inteiros e 2 casas decimais |
| `data` | Sim | Data real no formato `AAAA-MM-DD`, até o dia atual no fuso `America/Sao_Paulo` |
| `descricao` | Não | Até 200 caracteres, sem caracteres de controle; padrão vazio |

A listagem aceita os filtros `data_inicio`, `data_fim`, `tipo`, `limite` (1 a 200, padrão
50) e `deslocamento` (0 a 1.000.000, padrão 0).

## Erros

| Status | Quando | Corpo |
|---|---|---|
| 401 | Sem sessão válida | `{"detail": "Unauthorized"}` |
| 403 | Escrita sem token CSRF válido | `{"detail": "CSRF check Failed"}` |
| 404 | Movimentação inexistente ou de outra usuária, sem distinção | `{"detail": "..."}` |
| 409 | Reserva não configurada, ou operação que deixaria o saldo declarado negativo | `{"detail": "..."}` |
| 422 | Dados ou filtros inválidos | `{"detail": [{"type": "...", "loc": ["query", "filtros"], "msg": "..."}]}` |

O 409 também ocorre ao reduzir o saldo inicial ou excluir um aporte quando o saldo
declarado ficaria negativo.
