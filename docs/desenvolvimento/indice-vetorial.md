# Índice vetorial educativo

Execute na raiz do repositório, em um ambiente virtual.

```bash
python -m pip install -e './packages/ai[vector]'
python -m finance_ai.vector_index --db .runtime/chroma
```

O comando lê `knowledge/catalogo.json` por padrão. Use `--catalog` para outro
catálogo e `--root` para a raiz dos caminhos canônicos. Só entram PDFs com
`approved_for_ingestion: true`, cuja identidade é conferida pelo SHA-256 antes
da extração. Quando o catálogo registra uma revisão de ingestão,
só as páginas físicas selecionadas entram no índice e a citação acompanha
cada segmento nos metadados. As janelas e os IDs são gerados pelo
[chunking documental](chunking-documental.md). O relatório registra páginas
vazias. Falhas de extração ou fontes inteiramente sem texto interrompem a
reconstrução antes da escrita. Com zero fontes aprovadas, o comando retorna
`no_approved_sources` sem criar um banco.

Fontes com escopo `academic_local` entram apenas ao passar
`--academic-local`. Esse índice é para o protótipo acadêmico não comercial e
fica local, sem distribuição. Use um diretório separado para essa coleção.

## Reconstruir o protótipo acadêmico

Depois de clonar o repositório, rode na raiz com Python 3.12 a 3.14.

```bash
python3 scripts/preparar_indice_academico.py
```

O comando instala o extra `vector` em um ambiente virtual local na primeira
execução e reconstrói a seleção de páginas dos 20 PDFs do protótipo. A
primeira execução com conteúdo pode precisar de internet para baixar os
pesos. Os PDFs originais permanecem nos caminhos do catálogo. Use essa
seleção apenas no protótipo acadêmico local, não comercial.

O Chroma gerado fica em `.runtime/chroma-academico-local`. O relatório
`.runtime/indice-academico-local.json` guarda o nome da coleção para consultar
com a CLI `finance_ai.retrieval`, quando o módulo estiver disponível na
branch. O catálogo gerado e o banco ficam em `.runtime/`, ignorado pelo Git.
Execute o mesmo comando para reconstruir a coleção em outra máquina.

Com o módulo de recuperação disponível, consulte o índice local. Este exemplo
usa o interpretador do ambiente criado no macOS ou Linux.

```bash
colecao=$(python3 -c 'import json; print(json.load(open(".runtime/indice-academico-local.json"))["collection"])')
.runtime/venv-indice/bin/python -m finance_ai.retrieval \
  --db .runtime/chroma-academico-local --collection "$colecao" \
  'Como organizar as receitas e despesas no orçamento familiar?'
```

## Modelo e persistência

O modelo local [Multilingual E5 Small](https://huggingface.co/intfloat/multilingual-e5-small/tree/fd1525a9fd15316a2d503bf26ab031a61d056e98)
tem revisão fixada, suporta português e produz vetores de 384 dimensões. A
inferência roda em CPU com vetores float32 normalizados em lotes de 32. O
prefixo é `passage: ` para documentos e `query: ` para futuras consultas.
Entradas acima de 512 tokens são truncadas pelo modelo. A primeira indexação
com conteúdo pode baixar os pesos. A distância da coleção Chroma é cosseno.

A configuração e as versões das bibliotecas de indexação e inferência aparecem
no JSON de saída e nos metadados da coleção. A coleção
é identificada pelo hash da configuração e dos IDs dos chunks.
Reexecutar com os mesmos dados reaproveita os IDs persistidos. Se só a citação
de uma fonte mudar no catálogo, os embeddings são mantidos e os metadados dos
trechos já gravados são atualizados; o JSON de saída informa quantos em
`updated_metadata`. Se uma gravação
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
