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

## Uso pelos agentes

No backend, os agentes usam a função `executar_ferramenta(usuaria, nome, parametros)`, em
`apps/api/financas/ferramentas.py`. O orquestrador entrega a usuária da sessão, e o modelo
escolhe apenas `nome` e `parametros`.

| Exceção | Quando ocorre |
|---|---|
| `AcessoNegado` | Não há usuária autenticada |
| `FerramentaNaoPermitida` | O nome não está na lista de ferramentas |
| `ParametrosInvalidos` | Há parâmetro desconhecido, ausente ou inválido |

## Erros das rotas

| Status | Quando |
|---|---|
| 401 | Sem sessão válida |
| 405 | Método diferente de `GET` |
| 422 | Parâmetro desconhecido, ausente ou inválido |
