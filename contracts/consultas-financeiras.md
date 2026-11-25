# Contrato das consultas financeiras

Referência: [BE-06 / #88](https://github.com/anamattos2/grupo11challenge2/issues/88).
O contrato executável é o [openapi.json](openapi.json). Este guia resume as regras para
as telas e para os agentes de IA.

As consultas leem somente os registros declarados no próprio aplicativo. Elas não acessam
bancos externos e os valores não representam saldo bancário verificado.

## Regras de segurança

- Todas as rotas exigem sessão e usam somente o método `GET`.
- A usuária vem sempre da sessão. Parâmetros como `usuaria_id` e `sql` são recusados.
- Agentes só podem usar as ferramentas listadas neste contrato, com parâmetros tipados.
- Não existe ferramenta de escrita nem entrada de SQL.
- Mensagens de erro das ferramentas não devolvem o valor recebido.

## Ferramentas

| Ferramenta | Rota | Parâmetros | Resultado em `dados` |
|---|---|---|---|
| `totais_por_categoria` | `GET /api/consultas/totais-por-categoria` | `data_inicio`, `data_fim`, `tipo`, `categoria_id` | Receitas, despesas, resultado e total de cada categoria |
| `resumo_periodo` | `GET /api/consultas/resumo-periodo` | `data_inicio`, `data_fim` | Receitas, despesas, despesas essenciais e resultado |
| `consultar_reserva` | `GET /api/consultas/reserva` | `mes_inicio`, `mes_fim` | Meta, saldo declarado, cobertura e progresso |
| `saldos_contas` | `GET /api/consultas/saldos-contas` | Nenhum | Saldo declarado de cada conta e total |

`GET /api/consultas/ferramentas` devolve essa lista com o JSON Schema dos parâmetros.

| Parâmetro | Obrigatório | Regra |
|---|---|---|
| `data_inicio`, `data_fim` | Sim | `AAAA-MM-DD`, datas incluídas, período de até 731 dias |
| `tipo` | Não | `receita` ou `despesa` |
| `categoria_id` | Não | Número inteiro; categoria de outra usuária não retorna dados |
| `mes_inicio`, `mes_fim` | Não | `AAAA-MM`, enviados juntos, conforme [reserva.md](reserva.md) |

## Formato do resultado

Toda ferramenta devolve os mesmos campos de identificação:

| Campo | Conteúdo |
|---|---|
| `evidencia_id` | ID `fin-` seguido de 16 caracteres; repete quando consulta e dados são iguais |
| `tipo_evidencia` | Sempre `financeira`, para separar dos trechos educativos do RAG |
| `ferramenta` | Nome da ferramenta executada |
| `origem` | Sempre `registros_declarados` |
| `moeda` | Sempre `BRL` |
| `periodo` | `inicio` e `fim` consultados; `null` em `saldos_contas`, que mostra a posição atual |
| `parametros` | Parâmetros aplicados |
| `dados` | Resultado específico da ferramenta |

```http
GET /api/consultas/totais-por-categoria?data_inicio=2026-10-01&data_fim=2026-10-31
```

```json
{
  "evidencia_id": "fin-ae66c4396f740a07",
  "tipo_evidencia": "financeira",
  "origem": "registros_declarados",
  "moeda": "BRL",
  "periodo": {"inicio": "2026-10-01", "fim": "2026-10-31"},
  "parametros": {"data_inicio": "2026-10-01", "data_fim": "2026-10-31"},
  "ferramenta": "totais_por_categoria",
  "dados": {
    "receitas": "3000.00",
    "despesas": "2000.00",
    "resultado": "1000.00",
    "quantidade": 2,
    "categorias": [
      {
        "categoria_id": 1,
        "categoria_nome": "Moradia",
        "tipo": "despesa",
        "essencial": true,
        "total": "2000.00",
        "quantidade": 1
      },
      {
        "categoria_id": 2,
        "categoria_nome": "Salário",
        "tipo": "receita",
        "essencial": false,
        "total": "3000.00",
        "quantidade": 1
      }
    ]
  }
}
```

### Formato dos valores

Os valores são texto decimal com 2 casas. Somas de vários registros não cabem no
formato de um valor individual (até 12 dígitos inteiros) e têm formato próprio:

| Campos | Formato |
|---|---|
| Saldo de cada conta em `saldos_contas` | Valor individual: até 12 dígitos inteiros |
| `receitas`, `despesas`, `resultado` e `total` de `totais_por_categoria`; `receitas`, `despesas`, `despesas_essenciais` e `resultado` de `resumo_periodo`; `total_declarado` de `saldos_contas` | `^-?[0-9]{1,18}\.[0-9]{2}$`, o mesmo dos totais de `GET /api/transacoes` |
| Somas, média, saldo e meta de `consultar_reserva` | `^-?[0-9]{1,20}\.[0-9]{2}$` (ver [reserva](reserva.md)) |
| `progresso_percentual` e `meses_cobertos` | `^-?[0-9]{1,23}\.[0-9]{2}$`: passam de 100 ou de 12 dígitos quando o saldo é grande perto da meta ou da despesa mensal |

## Meta, saldo e cobertura

| Campo em `consultar_reserva` | Significado |
|---|---|
| `meta` | Despesas essenciais mensais × meses de cobertura |
| `saldo_declarado` | Saldo inicial + aportes − retiradas |
| `meses_cobertura` | Meses que a usuária deseja cobrir |
| `meses_cobertos` | Saldo declarado ÷ despesas essenciais mensais, com duas casas decimais |
| `progresso_percentual` | 100 × saldo declarado ÷ meta |
| `estado` | `calculado`, `meta_zero` ou `dados_insuficientes` |
| `faltando` | Informações necessárias que ainda não existem |

Campos que dependem de um dado ausente retornam `null`. O agente deve comunicar o que
falta, sem estimar o valor.

`consultar_reserva` e `GET /api/reserva` usam a mesma função (`resumir_reserva`), que lê
despesas, configuração e movimentações numa transação `REPEATABLE READ`. Uma alteração
concorrente do saldo inicial ou das movimentações aparece inteira ou não aparece: saldo,
`meses_cobertos` e progresso nunca combinam estados diferentes.

## Uso pelos agentes

No backend, os agentes usam a função `executar_ferramenta(usuaria, nome, parametros)`, em
`apps/api/financas/ferramentas.py`. O orquestrador entrega a usuária da sessão, e o modelo
escolhe apenas `nome` e `parametros`.

| Exceção | Quando ocorre |
|---|---|
| `AcessoNegado` | Não há usuária autenticada |
| `FerramentaNaoPermitida` | O nome não está na lista de ferramentas |
| `ParametrosInvalidos` | Há parâmetro desconhecido, ausente ou inválido |

### Integração com o Research Agent (S6-01 / #99)

O contrato dos agentes (S4-01 / #75) já está concluído, e o adaptador
`FonteFinanceiraBackend`, em `packages/ai/src/finance_ai/agents/backend.py`, converte as
duas pontas sem alterar esta API:

| Operação do Research Agent | Ferramenta chamada |
|---|---|
| `resumo_transacoes` com `somente_essenciais` | `resumo_periodo` (usa `despesas_essenciais`) |
| `resumo_transacoes` | `totais_por_categoria` |
| `listar_contas` | `saldos_contas` |
| `situacao_reserva` | `consultar_reserva` |

- **ID de evidência:** o Research Agent exige `fin:<operacao>:<12 hex>`. O adaptador gera
  esse ID com `id_financeiro(operacao, parametros)`, a partir da operação e dos parâmetros
  dos agentes, e guarda o `evidencia_id` desta API (`fin-<16 hex>`) em
  `localizacao.filtros["evidencia_backend"]`, junto do nome da ferramenta. Assim a
  citação mostrada pelos agentes continua rastreável até a consulta feita aqui.
- **Usuária:** o adaptador recebe a `usuaria_ref` opaca do `ContextoAutorizado` e só a
  troca pela usuária da sessão por meio de `resolver_usuaria`; sem correspondência, falha
  com `contexto_ausente`. Os agentes nunca enviam a identidade nos parâmetros.
- **Erros:** o código `acesso_negado` vira `permissao_ausente` (negação da fonte). As
  demais exceções mantêm o `codigo` desta API, ou viram `ferramenta_indisponivel`, e uma
  resposta de outra ferramenta ou sem `tipo_evidencia` financeira vira `resposta_invalida`.

## Erros das rotas

| Status | Quando |
|---|---|
| 401 | Sem sessão válida |
| 405 | Método diferente de `GET` |
| 422 | Parâmetro desconhecido, ausente ou inválido |
