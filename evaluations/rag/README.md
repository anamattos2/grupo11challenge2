# Dataset e gabarito RAG

A versão 1.0.0 fornece perguntas em português para comparar LLM puro, RAG e
RAG com explicação. As situações e valores das perguntas são fictícios. As
respostas foram redigidas para este conjunto e apontam para páginas físicas
no [catálogo de fontes](../../knowledge/catalogo.json). Os arquivos contêm
referências por ID e página.

- [Dataset](dataset.json) — ID, partição e pergunta. Somente a pergunta é enviada
  ao sistema avaliado.
- [Gabarito](gabarito.json) — comportamento esperado, evidências de referência,
  resposta de exemplo e critérios mínimos. Uso exclusivo dos avaliadores.

| Partição | Com evidência | Informação insuficiente | Fora de escopo | Total |
| --- | ---: | ---: | ---: | ---: |
| Calibração | 4 | 1 | 1 | 6 |
| Avaliação | 8 | 2 | 2 | 12 |

As fontes de referência das duas partições são disjuntas. Isso não implica
separar os documentos do índice, que deve permanecer idêntico entre as variantes
que usam RAG. Calibre prompts, limiar e parâmetros usando somente a calibração.
Ao iniciar a avaliação, fixe versão do dataset, revisão do código, coleção e
configuração de cada variante. Preserve os resultados e conte falhas de execução
no total de casos planejados.

## Critérios de revisão

| Comportamento esperado | O que verificar |
| --- | --- |
| Com evidência | A resposta satisfaz todos os critérios do caso e evita afirmações adicionais sem suporte. Para RAG, a citação deve corresponder ao trecho usado. Uma página alternativa pode ser aceita se o revisor confirmar o suporte e registrar a decisão. Para LLM puro, confira o suporte no gabarito. |
| Informação insuficiente | A resposta identifica o dado faltante e mantém a conclusão em aberto. Pode explicar como prosseguir. |
| Fora de escopo | A resposta declara o limite e evita inventar acesso, resultado ou ação concluída. |

Registre por caso e variante o ID, o avaliador, o resultado de cada critério,
a qualidade da citação quando aplicável e a justificativa em caso de falha.
Informe os resultados por classe e os denominadores. Uma página de referência
ausente do índice deve ser registrada como lacuna de cobertura, sem excluir o
caso da avaliação.

## Revisores

A revisão humana está pendente. O responsável pela issue coordena a indicação
dos revisores no PR.

| Função | Responsabilidade | Identificação |
| --- | --- | --- |
| Revisor de conteúdo | Conferir unicidade, escopo e suporte nas páginas do catálogo | A indicar pela equipe |
| Revisor de avaliação | Conferir a separação das partições, os critérios e o tratamento de falhas | A indicar pela equipe |

Registre no PR o nome ou login de quem revisou, o commit revisado, a data e as
decisões sobre divergências. Congele a versão após essa revisão e antes de
executar a comparação final.

O [baseline LLM puro](baseline-llm.md) executa as perguntas e registra as
respostas, latências e falhas para revisão posterior.

A [variante LLM com RAG](variante-rag.md) registra as evidências recuperadas
e as abstenções para comparação com o baseline.
