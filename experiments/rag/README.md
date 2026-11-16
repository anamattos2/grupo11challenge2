# Experimentos RAG preservados

Nesta etapa, este diretório indexa os experimentos sem mudar seus caminhos.
A migração física deve atualizar referências e ter verificação própria.

| Origem preservada | Conteúdo |
|---|---|
| [rag_notebook.ipynb](../../rag_notebook.ipynb) | Experimento LangChain / Ollama |
| [rag_educacao_financeira.ipynb](../../rag_educacao_financeira.ipynb) | Experimentos de educação financeira e avaliação |
| [RAG/projeto-rag](../../RAG/projeto-rag) | Scripts de ingestão, consulta e avaliação |
| [requirements.txt](../../requirements.txt) | Dependências históricas dos notebooks |
| [requirements dos scripts](../../RAG/projeto-rag/requirements.txt) | Dependências históricas do protótipo |

Os manifests históricos não têm versões fixadas e não garantem reprodução.
Não os instale no ambiente mínimo do monorepositório. Não executar
`indexar.py` automaticamente: o script pode apagar e recriar a coleção Chroma.
Notebooks dependem de arquivos, modelos e sequência de células.

O [inventário](../../docs/desenvolvimento/legado-inventario.json) registra paths
exatos e blobs Git, incluindo colisões de normalização Unicode.
O [guia](../../docs/desenvolvimento/ambiente.md) explica como verificá-lo.
