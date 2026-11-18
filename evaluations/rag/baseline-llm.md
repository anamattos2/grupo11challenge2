# Baseline LLM puro

A variante executa as perguntas do [dataset](dataset.json) individualmente
em um Ollama local. Cada chamada envia o prompt de sistema e uma pergunta.
O gabarito, o catálogo e o Chroma ficam fora da chamada.

Instale o pacote base em um ambiente virtual e deixe o Ollama local em
execução. O modelo padrão é [Qwen2.5 0.5B Instruct](https://ollama.com/library/qwen2.5:0.5b).
A primeira configuração baixa os pesos.

```bash
python -m pip install -e ./packages/ai
ollama pull qwen2.5:0.5b
python -m finance_ai.llm_baseline
```

O padrão roda a calibração. Use `--split avaliacao` após congelar a
configuração e o dataset, conforme o [protocolo](README.md). Use a mesma
revisão do modelo, o mesmo contrato e parâmetros de geração comparáveis nas
variantes seguintes. A tag do modelo pode mudar com um novo download.
Compare o digest registrado antes de reunir resultados de execuções
diferentes.

| Configuração | Valor padrão |
| --- | --- |
| Modelo | `qwen2.5:0.5b`, com digest e versão do Ollama registrados |
| Geração | Temperatura 0, seed 42, limite de 256 tokens de saída |
| Contexto | 2.048 tokens |
| Tempo limite | 120 s por requisição |
| Registro | JSONL em `.runtime/avaliacoes/`, um arquivo novo por execução |

O JSONL contém um cabeçalho com a revisão do código e o estado da árvore,
hash do dataset, partição, modelo, prompt e parâmetros. Cada linha de caso
preserva pergunta, resposta, latência, motivo de término e eventual erro. A
latência é medida no cliente e pode incluir o carregamento do modelo.
Se o servidor ou modelo estiver indisponível, cada caso planejado fica
registrado como `not_run`. O comando retorna código 1 quando há erro ou
caso não executado. Uma execução interrompida pode ficar sem a linha de resumo.

A contagem `ok` indica respostas recebidas. A classificação de qualidade
pertence à revisão posterior com o gabarito.

## Execução de calibração

Em 18/11/2026, o Ollama 0.32.5 executou os seis casos de calibração com o
modelo Q4_K_M de digest
`a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67`.
Foram recebidas seis respostas, com latências entre 566 e 2.234 ms. Duas
atingiram o limite de geração (`CAL-03` e `CAL-06`). O JSONL original
ficou em `.runtime/avaliacoes/`. A partição de avaliação foi preservada
para a comparação final.

## Calibração do prompt

O comando mantém `original-v1` como padrão e disponibiliza o prompt
`direto-v2`, que pede até três frases e diferencia resposta educativa,
dados insuficientes e pedido fora de escopo.

```bash
python -m finance_ai.llm_baseline --prompt direto-v2
```

Com o mesmo digest do modelo e os mesmos parâmetros, as duas execuções
retornaram seis respostas. Na revisão preliminar pelo gabarito, a aprovação
passou de 0/6 para 1/6 e os términos por limite de geração passaram de 2/6
para 0/6. A latência mediana observada caiu de 1.390 ms para 514 ms, com
uma execução por prompt. A comparação é descritiva e aguarda revisão humana.

## Comparação com modelo maior

Para isolar a mudança de modelo, mantenha o prompt e a configuração de
geração da calibração anterior.

```bash
ollama pull qwen2.5:3b
python -m finance_ai.llm_baseline --model qwen2.5:3b --prompt direto-v2
```

O Qwen2.5 3B Q4_K_M, digest
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`,
retornou seis respostas completas. Com o prompt `direto-v2`, os dois
tamanhos aprovaram 1/6 casos na revisão estrita preliminar. A latência
mediana observada foi de 514 ms no 0,5B e 1.195 ms no 3B. Essa execução
não sustentou uma troca de modelo com base no gabarito. Os 12 casos de
avaliação continuam reservados.
