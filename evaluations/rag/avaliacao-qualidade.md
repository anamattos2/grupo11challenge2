# Comparação de qualidade, suporte e citações

## Calibração de 18/11/2026

Revisão preliminar por Codex. Revisão humana de conteúdo e de avaliação
pendente no [protocolo do dataset](README.md). Foram executados os seis casos
de calibração nas três variantes. Os 12 casos de avaliação permanecem reservados.

| Item | Configuração comum |
| --- | --- |
| Código | `b402ebfa130f3b89d7aef50c0291356dc6ffcb2f`, árvore limpa durante as execuções |
| Dataset | v1.0.0, SHA-256 `d82a7cf3b323b8f915bef365c8984fc5cc11fd3ba54bcf9a2a4a1edf20978591` |
| Gerador | Qwen2.5 3B Q4_K_M, digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`, Ollama 0.32.5 |
| Prompt e geração | `direto-v2`, temperatura 0, seed 42, limite 256 tokens e contexto de 2.048 tokens |
| Acervo das variantes RAG | 20 PDFs originais, 27 páginas selecionadas e 87 trechos. Coleção `educativo-661f57db5ded91dc8ffc6fea4b4a86699e8df103a0a3ebd1069971526e24c682` |
| Busca | Até cinco candidatos, similaridade mínima 0,85. As duas variantes recuperaram as mesmas páginas. |
| Escopo | Execução acadêmica local. A triagem experimental ficou fora da comparação. |

## Resultados

| Indicador | LLM puro | RAG | RAG com explicação |
| --- | ---: | ---: | ---: |
| Casos executados / planejados | 6/6 | 6/6 | 6/6 |
| Casos aprovados pelo gabarito, todas as classes | 1/6 | 1/6 | 2/6 |
| M03 · Correção integral nos casos respondíveis | 1/4 | 1/4 | 2/4 |
| M04 · Respostas entregues pelo modelo com afirmação material sem suporte | 2/6 | 2/4 | 0/5 |
| M05 · Pares afirmação–citação que sustentam a afirmação entregue | N/A (0 pares) | 2/4 | 7/7 |
| M02 · Página de referência entre os cinco candidatos | N/A | 4/4 | 4/4 |
| M07 · Abstenção adequada pelo gabarito nos casos sem suporte | 0/2 | 0/2 | 0/2 |
| Abstenções registradas pelo executor | 0/6 | 2/6 | 1/6 |
| Falhas técnicas | 0/6 | 0/6 | 0/6 |
| Mediana / p95 da latência total | 1.103 / 1.909 ms | 3.849 / 6.451 ms | 2.413 / 4.600 ms |

No M01, as quatro páginas de referência dos casos respondíveis estavam
disponíveis (4/4). Nenhum caso foi excluído. M02 usa documento e página como
unidade nesta calibração. A presença de uma página no top 5 e a fidelidade
textual da citação são verificações diferentes da pertinência da resposta.

M03 inclui recusas indevidas no denominador de quatro casos respondíveis.
M04 considera respostas entregues, verificando afirmações materiais contra
a pergunta e o gabarito no LLM puro, e também contra os trechos no RAG. Uma
abstenção fixa do executor fica fora desse denominador. No LLM puro,
foram sinalizadas a definição restritiva de orçamento como planilha
e a classificação condicional que desconsiderou que o aluguel era recebido.
No RAG, foram sinalizados o pedido de um dado que a pergunta já fornecia
e a apresentação de um valor de exemplo como se respondesse pelo gasto pessoal.

Para M05, cada referência explícita a uma afirmação entrou no denominador.
Conferi as onze referências por hash, página e offsets no texto limpo dos
PDFs. As quatro referências do RAG e as sete do RAG com explicação existiam.
No RAG comum, duas sustentavam a afirmação associada. No estruturado, as
sete correspondiam às frases reproduzidas, incluindo frases irrelevantes
para a pergunta. O caso descartado pelo RAG comum por falta de citação
fica registrado como abstenção. Sua saída bruta não continha uma referência.

M07 exige o pedido do dado faltante pertinente ou uma declaração clara de
fora de escopo, conforme o caso. A abstenção documental genérica fica
visível na contagem de abstenções e não satisfaz esse critério para a
impressora. As latências incluem a busca nas variantes RAG. Com seis casos,
o p95 por posto mais próximo é a maior observação. A ordem de execução e
o carregamento do modelo podem influenciar as durações.

## Revisão por caso

| Caso | LLM puro | RAG | RAG com explicação |
| --- | --- | --- | --- |
| CAL-01 | Parcial. Cita receitas e despesas mensais, mas omite previsão e restringe o formato a planilha. | Parcial. F001 p. 21 sustenta a distinção entre planejar gastos e registrar o passado, mas faltou incluir receitas previstas. | Parcial. A frase de F001 p. 21 trata do déficit previsto, sem distinguir orçamento de histórico. |
| CAL-02 | Incorreto. Trata os dois lançamentos como possíveis saídas na mesma coluna. | Recusa indevida. Pede a classificação do aluguel já indicada na pergunta. F003 p. 4 não sustenta essa necessidade. | Incorreto. Citação literal de F003 p. 4 sobre fluxo de caixa, sem classificar os dois lançamentos. |
| CAL-03 | Parcial. Explica o acompanhamento, sem dizer que os pequenos desembolsos integram o total. | Recusa indevida. Abstenção por falta de citação, apesar de F019 p. 8 estar entre os candidatos. | Correto. F019 p. 8 relaciona os pequenos gastos ao total e ao acompanhamento. |
| CAL-04 | Correto. Reconhece a revisão da meta. | Correto. F001 p. 20 sustenta a revisão da meta. | Correto. Duas frases de F001 p. 20 sustentam a revisão. |
| CAL-05 | Parcial. Pede valor médio de uma viagem, insuficiente para apurar o total mensal. | Incorreto. Apresenta um valor de exemplo. A citação F019 p. 8 não sustenta um valor pessoal. | Incorreto. Duas frases de F019 p. 8 existem, mas são genéricas e não fornecem os lançamentos da pessoa. |
| CAL-06 | Incorreto. Reconhece o limite, mas oferece instruções de conserto. | Abstenção genérica. A busca não encontrou trecho e a resposta não declarou o limite de escopo. | Abstenção genérica pelo mesmo motivo. |

## Repetir e revisar

O [guia do baseline](baseline-llm.md) e os guias do
[RAG](variante-rag.md) e da [explicação](explicacao-estruturada.md)
documentam a instalação. Com o Ollama e a coleção acadêmica locais:

```bash
COLECAO=$(python -c 'import json; print(json.load(open(".runtime/indice-academico-local.json"))["collection"])')
DESTINO=.runtime/avaliacoes/issue-73
python -m finance_ai.llm_baseline --split calibracao --model qwen2.5:3b \
  --prompt direto-v2 --output-dir "$DESTINO"
python -m finance_ai.llm_rag --split calibracao --model qwen2.5:3b \
  --prompt direto-v2 --db .runtime/chroma-academico-local --collection "$COLECAO" \
  --output-dir "$DESTINO"
python -m finance_ai.llm_rag_explained --split calibracao --model qwen2.5:3b \
  --prompt direto-v2 --db .runtime/chroma-academico-local --collection "$COLECAO" \
  --output-dir "$DESTINO"
```

Os JSONL contêm respostas, fontes e latências por caso. Eles permanecem
em `.runtime/`. Antes da execução oficial, registre os revisores, resolva as
divergências e congele a configuração. Para a avaliação final, registre
também M06 por afirmação, incluindo aquelas sem citação.
