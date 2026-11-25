# Variante LLM com RAG

O comando usa as mesmas perguntas, o mesmo gerador Ollama e o mesmo formato
de execução do [baseline LLM puro](baseline-llm.md). A variante recebe uma
coleção Chroma criada conforme o [guia do índice](../../docs/desenvolvimento/indice-vetorial.md).
Instale o extra `vector`, inicie o Ollama e disponibilize o modelo escolhido.

```bash
python -m pip install -e './packages/ai[vector]'
python -m finance_ai.llm_baseline --prompt direto-v2
python -m finance_ai.llm_rag --db .runtime/chroma-academico-local --collection "$COLECAO"
```

Defina `COLECAO` com o nome informado pelo indexador. Os comandos executam a
calibração por padrão. Compare execuções com o mesmo digest do modelo,
`--prompt direto-v2`, versão do dataset e parâmetros de geração. Antes de
rodar `--split avaliacao`, siga o [protocolo de revisão](README.md).

## Busca, geração e abstenção

- A busca usa a coleção indicada, até cinco trechos e score mínimo de
  0,85. Use `--limit` ou `--min-score` para calibrar.
- Sem evidência, o fluxo responde com uma abstenção e pula a chamada de geração.
  Falhas técnicas de recuperação são registradas como erro de execução.
- Com evidência, os trechos recebem referências numéricas locais. Se a
  geração atingir o limite ou devolver citações ausentes ou fora da faixa,
  o fluxo registra a saída bruta e entrega uma abstenção.
- As citações reconhecidas são mapeadas para ID, documento e página pelo
  programa. A conferência de que o trecho sustenta a afirmação cabe ao
  avaliador humano. A triagem experimentada separadamente segue em calibração.

O JSONL fica em `.runtime/avaliacoes/`. O cabeçalho registra modelo,
digest, prompt, parâmetros e coleção. Cada caso preserva pergunta, resposta,
evidências, citações, latência total, latências por etapa e eventual falha
ou motivo de abstenção. `ok` indica que a resposta foi entregue com uma
referência válida no contexto. A contagem de qualidade vem do gabarito.

## Verificação

```bash
python -m unittest discover -s tests -p 'test_llm_rag.py'
```

O teste usa uma fonte fictícia para verificar preservação da evidência,
abstenção sem resultado, rejeição de citações inválidas e registro de falhas.

Na demonstração local com Chroma e Ollama reais, um PDF fictício descrevia
a finalidade de uma reserva de emergência. O Qwen2.5 3B respondeu com
uma citação mapeada à página 1 do documento `RESERVA`. O Qwen2.5 0,5B
produziu referência inválida e o fluxo se absteve. A pergunta sobre
conserto de impressora ficou sem evidência e sem chamada de geração
nas duas execuções. Essa demonstração verifica o fluxo e a rastreabilidade.
