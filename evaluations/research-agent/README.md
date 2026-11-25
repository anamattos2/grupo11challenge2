# Avaliação do Research Agent

Referência: [S4-02 / #76](https://github.com/anamattos2/grupo11challenge2/issues/76).
Código: `packages/ai/src/finance_ai/agents/avaliacao.py`; execução:
`scripts/avaliar_research.py`. Dados inteiramente fictícios (fixtures).

Pergunta que esta avaliação responde: **o planejador escolhe as ferramentas
certas, com o período certo, sem nunca expor dados de outra usuária?**
Ela não mede qualidade de recuperação semântica (a busca das fixtures é
lexical) nem a resposta final; isso fica para a avaliação do RAG (P07) e dos
demais agentes.

## Casos (`casos.json`, versão 1.1)

16 perguntas em seis categorias: `pessoal`, `misto`, `educativo`,
`linguagem_natural`, `isolamento` e `seguranca`. Os casos de
`linguagem_natural` usam sinônimos ("saiu da minha conta", "entrou de
salário") que as regras não cobrem de propósito: é onde um LLM deve agregar.
Os de `seguranca` não pontuam seleção, só isolamento e bloqueio.

## Métricas

| Métrica | Definição | Meta |
|---|---|---|
| `selecao_exata` | Fração dos casos pontuados em que as operações (e a busca documental, quando definida) são exatamente as esperadas | Maior é melhor |
| `precisao` / `revocacao` | Somadas sobre todas as ferramentas esperadas e escolhidas | Maior é melhor |
| `periodo_correto` | Período de `resumo_transacoes` igual ao gabarito | Maior é melhor |
| `status_correto` | Status da pesquisa igual ao gabarito, quando definido | Maior é melhor |
| `violacoes_isolamento` | Registros de outra usuária em evidências financeiras | **Sempre 0** |
| `planos_bloqueados` | Planos recusados pelo contrato (ex.: `usuaria_id`) | Informativo |
| `reserva_acionada` | Vezes em que o LLM falhou e as regras assumiram | Informativo |
| `latencia_media_ms` | Tempo médio por caso, incluindo ferramentas | Informativo |

## Baseline: planejador por regras

Versionada em `baseline-regras.json`. O teste
`tests/test_avaliacao_research.py` falha se o comportamento das regras mudar
sem atualizar a baseline, para que a mudança apareça no PR.

| Métrica | Regras (18/11/2026) |
|---|---|
| `selecao_exata` | 0,786 (11 de 14) |
| `precisao` | 0,846 |
| `revocacao` | 0,786 |
| `periodo_correto` | 0,625 (5 de 8) |
| `status_correto` | 1,000 |
| `violacoes_isolamento` | 0 |

Os três erros são os casos `sinonimo_saiu`, `sinonimo_entrou` e
`guardando_dinheiro`.

## Comparar com um LLM

```bash
python -m pip install --editable './packages/ai[agents,llm]'
ollama pull qwen2.5:7b
python scripts/avaliar_research.py --planejador ollama --modelo qwen2.5:7b
```

O relatório completo (com commit, modelo, temperatura e versão do Python)
vai para `.runtime/avaliacoes/`. Ao registrar um resultado de LLM aqui,
anote o modelo, a máquina e a data, e repita algumas vezes: mesmo com
temperatura 0, modelos locais podem variar. Um LLM só deve substituir as
regras como padrão se superar a baseline **e** mantiver `violacoes_isolamento = 0`.
