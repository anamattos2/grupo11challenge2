# Recuperação documental

Instale o extra `vector` e use a coleção retornada após uma execução
bem-sucedida do [índice vetorial](indice-vetorial.md).

```bash
python -m finance_ai.retrieval --db .runtime/chroma \
  --collection "$COLECAO" 'Para que serve a reserva de emergência?'
```

O módulo também expõe `search_evidence(db_path, collection_name, query)` para
consumidores Python. A consulta usa o mesmo modelo, revisão e configuração
registrados na coleção, com o prefixo de consulta `query: `. O máximo padrão é
de cinco resultados. Para restringir a um documento, passe `--document-id`
ou o argumento `document_id`.

## Contrato JSON v1

O retorno contém `schema_version`, `status`, `evidencias` e `error`. Cada
evidência inclui `chunk_id`, `document_id`, `source_sha256`, `page_number`,
`start`, `end`, `text` e `score`. Os offsets usam o texto limpo da página,
com início inclusivo e fim exclusivo.

- `ok` contém evidências ordenadas por similaridade de cosseno.
- `empty_query` indica consulta vazia ou composta por espaços.
- `no_results` indica coleção vazia ou ausência de resultados após filtro e limiar.
- `error` retorna lista vazia e um código estável. Os códigos são
  `index_not_found`, `dependency_unavailable`, `collection_not_found`,
  `incompatible_collection`, `index_read_failed`, `embedding_failed` e
  `index_query_failed`. O comando retorna código de saída 1 nesse caso.

O score é `1 - distância de cosseno`. O limiar inicial de 0,85 é configurável
com `--min-score` ou `min_score`. Ele separou o trecho pertinente do trecho
distrator no exemplo fictício. A calibração para o corpus educativo depende
de avaliação posterior. O score mede similaridade, sem quantificar a
confiabilidade da fonte ou a correção de uma resposta.

## Demonstração reproduzível

```bash
FINANCE_AI_TEST_REAL_MODEL=1 python -m unittest discover -s tests -p 'test_retrieval.py'
```

A demonstração gera dois PDFs fictícios, reconstrói uma coleção temporária
e consulta a finalidade de uma reserva de emergência. Ela verifica o trecho
sobre despesas essenciais, vinculado à página 1 do PDF `RESERVA`. A execução
com o modelo real pode baixar os pesos fixados no índice.
