# Evidências locais — S4-01 / #75

Verificação em 18/11/2026, branch `feat-75-contratos-agentes`, a partir da
`main` em `1f44a3c`. Dados inteiramente fictícios. Este registro não substitui
revisão e merge do PR.

## O que foi entregue

- Modelos Pydantic dos contratos: `packages/ai/src/finance_ai/agents/contratos.py`.
- Política de fluxo executável: `packages/ai/src/finance_ai/agents/fluxo.py`.
- Fluxo como grafo LangGraph: `packages/ai/src/finance_ai/agents/grafo.py`, com
  diagrama gerado em `contracts/agentes/fluxo.mmd`.
- 11 JSON Schemas gerados em `contracts/agentes/schemas/`.
- 20 exemplos válidos e 18 inválidos em `contracts/agentes/exemplos/`.
- Documentação: `docs/arquitetura/agentes/contratos-agentes.md`.
- Extra `agents` (`pydantic==2.12.4`, `langchain-core==1.8.3`, `langgraph==1.2.22`)
  e passo de CI que confere schemas e diagrama.

## Ambiente limpo (equivalente à CI)

```text
python3 -m venv /tmp/ci-venv
/tmp/ci-venv/bin/python -m pip install --editable './packages/ai[documents,agents]'
/tmp/ci-venv/bin/python -m pip check
No broken requirements found.

/tmp/ci-venv/bin/python scripts/exportar_schemas_agentes.py --check
OK: 11 schemas e o diagrama do fluxo atualizados.

/tmp/ci-venv/bin/python -m unittest discover -s tests
Ran 49 tests ... OK

python3 scripts/verificar_catalogo.py
24 conteúdos únicos; 20 PDFs identificados; 39 caminhos preservados; 0 fontes aprovadas para ingestão.

python3 scripts/verificar_legado.py
OK: 70 arquivos históricos preservados no índice e no worktree.
```

Python local: 3.13. A CI usa 3.12; os modelos não usam recursos posteriores.

## O que os testes cobrem

| Teste | Verifica |
|---|---|
| `test_todo_schema_tem_exemplo_valido` | Cada um dos 11 contratos tem pelo menos um exemplo válido |
| `test_exemplos_invalidos_sao_recusados_pelo_motivo_esperado` | Cada inválido falha com o tipo de erro declarado |
| `test_arquivos_estao_sincronizados_com_os_modelos` | Schemas versionados iguais aos gerados |
| `test_nenhum_contrato_aceita_identidade_da_usuaria_fora_do_contexto` | Só o `ContextoAutorizado` tem campo de usuária |
| `test_papeis_tem_saidas_distintas` | Saídas dos quatro papéis não se sobrepõem |
| `test_reprovacao_permite_uma_revisao_e_depois_abstem` | Reprovação → revisão única → abstenção |
| `test_communication_nao_pode_usar_afirmacao_nao_aprovada` | Checagem final bloqueia texto sem aprovação |
| `test_saida_de_llm_fora_do_contrato_vira_erro_tratavel` | JSON gerado inválido vira `ContratoInvalido`, não resposta |
| `GrafoTest` (11 testes) | O grafo LangGraph percorre cada caminho: resposta, abstenção, complemento, revisão, falhas e diagrama sincronizado |

## Limites

Nenhum LLM é chamado. Analysis, Validation e Communication não estão
implementados; os testes do grafo usam agentes falsos que devolvem os exemplos.
Timeouts reais, checkpointer e rastros completos ficam para a S4-06 (#80).
O merge com `feat-67-recuperacao-documental` exigirá juntar as linhas de
`[project.optional-dependencies]` do `pyproject.toml` (conflito trivial).

## Ajustes da revisão do PR #135 (23/11/2026)

A revisão pediu quatro ajustes; o mapa pedido → mudança → teste está na seção
9 de `docs/arquitetura/agentes/contratos-agentes.md`. Resumo:

1. **Texto final**: a Communication devolve `paragrafos` ligados a afirmações
   aprovadas. O orquestrador confere afirmações, números e cobertura e monta
   texto, citações, fontes e ligações; se a redação não passar, usa o texto
   literal das afirmações aprovadas.
2. **Cálculo pela Analysis**: `PedidoCalculo` e status `precisa_calculo`; a
   Research executa `chamadas_solicitadas` com `pedido_id`; uma rodada, depois
   abstenção `calculo_indisponivel`.
3. **Falha × busca vazia**: status derivado por `status_da_pesquisa`; novo
   `sem_permissao`; erro de ferramenta sempre vira `falha`.
4. **Isolamento**: tuplas e `MappingProxyType` em todos os contratos; o grafo
   copia cada objeto entre agentes.

Exemplos: 25 válidos e 25 inválidos (antes 20 e 18).

```text
python -m pip install --editable './packages/ai[documents,agents]'   # ambiente limpo
python -m pip check                               → No broken requirements found.
python scripts/exportar_schemas_agentes.py --check → OK: 11 schemas e o diagrama do fluxo atualizados.
python -m unittest discover -s tests              → Ran 68 tests ... OK
```

Mesmo resultado em Python 3.12 (versão da CI) e 3.14. Em 3.14 o
`langchain-core` emite um aviso sobre a camada `pydantic.v1`, sem efeito nos testes.

## Correção após a segunda revisão (23/11/2026)

O PR #135 foi mesclado em `59c6a19`. A segunda revisão encontrou um bloqueante
(`KeyError` quando a Validation aprova um id que não existe na análise) e
quatro sugestões. As correções estão na branch `fix-75-referencias-entre-etapas`,
a partir da `main` em `7683484`; o mapa ponto → mudança → teste está no fim de
`docs/arquitetura/agentes/contratos-agentes.md`.

```text
python -m pip install --editable './packages/ai[documents,agents]'   # ambiente limpo
python scripts/exportar_schemas_agentes.py --check → OK
python -m unittest discover -s tests              → OK
python -m unittest tests.test_grafo_exaustivo     → 2 testes, 2.688 combinações do grafo, ~5 s
```

Prova de que os testes exaustivos detectam o problema: rodados contra o
código da `main` antes da correção, falham com
`('concluida', 'ok', 'aprova_id_fantasma', 'fiel'): exceção escapou do fluxo: KeyError('a9')`
e nos 8 casos de `negada` + `sem_resultados` classificados como `sem_evidencias`.
