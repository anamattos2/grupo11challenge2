# Chunking documental

O comando segmenta o campo `text` do [relatório de extração](extracao-documental.md).
Use o JSON produzido pela extração como entrada.

```bash
python -m finance_ai.chunking extracao.json > chunks.json
```

O padrão é de 1.000 caracteres Unicode por janela, com 150 de sobreposição
(15%). O tamanho limita o volume de texto por segmento. A sobreposição mantém
parte do contexto quando uma frase cruza um corte, com duplicação limitada.
São valores iniciais configuráveis com `--size` e `--overlap`. Os limites
são em caracteres Unicode e podem cortar palavras. A contagem de tokens
depende do modelo usado em uma etapa posterior.

Cada janela pertence a uma única página física, numerada a partir de 1. Os
campos `start` e `end` são offsets no texto limpo da página, com início
inclusivo e fim exclusivo. O passo é `size - overlap`. A última janela
termina no fim do texto e pode ser menor. Páginas vazias e com erro ficam
fora da segmentação, e o JSON mantém o estado e as ocorrências da extração.

Para reproduzir o resultado, use o mesmo relatório e os parâmetros registrados
em `parameters`. Cada ID é o SHA-256 da lista JSON compacta em UTF-8, com
caracteres Unicode preservados, contendo nesta ordem a versão do algoritmo,
tamanho, sobreposição, ID do documento, SHA-256 da fonte, página, início, fim e
texto do segmento. O caminho local do PDF fica fora do cálculo do ID.

As evidências de segmentação e rastreabilidade usam um relatório de extração fictício.
```bash
python -m unittest discover -s tests -p 'test_chunking.py'
```
