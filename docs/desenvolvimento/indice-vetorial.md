# Índice vetorial educativo

Execute na raiz do repositório, em um ambiente virtual.

```bash
python -m pip install -e './packages/ai[vector]'
python -m finance_ai.vector_index --db .runtime/chroma
```

O comando lê `knowledge/catalogo.json` por padrão. Use `--catalog` para outro
catálogo e `--root` para a raiz dos caminhos canônicos. Só entram PDFs com
`approved_for_ingestion: true`, cuja identidade é conferida pelo SHA-256 antes
da extração. As janelas e os IDs são gerados pelo
[chunking documental](chunking-documental.md). O relatório registra páginas
vazias. Falhas de extração ou fontes inteiramente sem texto interrompem a
reconstrução antes da escrita. Com zero fontes aprovadas, o comando retorna
`no_approved_sources` sem criar um banco.

## Modelo e persistência

O modelo local [Multilingual E5 Small](https://huggingface.co/intfloat/multilingual-e5-small/tree/fd1525a9fd15316a2d503bf26ab031a61d056e98)
tem revisão fixada, suporta português e produz vetores de 384 dimensões. A
inferência roda em CPU com vetores float32 normalizados em lotes de 32. O
prefixo é `passage: ` para documentos e `query: ` para futuras consultas.
Entradas acima de 512 tokens são truncadas pelo modelo. A primeira indexação
com conteúdo pode baixar os pesos. A distância da coleção Chroma é cosseno.

A configuração e as versões das bibliotecas de indexação e inferência aparecem
no JSON de saída e nos metadados da coleção. A coleção
é identificada pelo hash da configuração e da sequência de IDs dos chunks.
Reexecutar com os mesmos dados reaproveita os IDs persistidos. Se uma gravação
em lotes for interrompida, a próxima execução completa os IDs faltantes com
`upsert`. Mudanças nos chunks ou na configuração geram outra coleção. Use o
nome retornado após uma execução bem-sucedida para acessar a versão
reconstruída. Coleções anteriores continuam no diretório. A reprodução é
lógica, com os mesmos IDs e configuração, e pode haver diferenças numéricas
entre ambientes de execução.

## Validação com fontes fictícias

```bash
python -m unittest discover -s tests -p 'test_vector_index.py'
```

O teste de integração usa o Chroma persistente e vetores controlados para
verificar a reconstrução, a repetição e a preservação da coleção anterior.
