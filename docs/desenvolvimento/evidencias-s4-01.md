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
