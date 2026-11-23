# Pacote de IA

Base instalável para RAG, quatro agentes, orquestração e processamento de imagens.
Inclui extração e limpeza local de texto de PDFs com rastreabilidade por página.
RAG, agentes, orquestração e OCR ainda não estão implementados neste pacote.

A instalação não importa os experimentos nem baixa modelos. O pacote não possui
dependências de execução na instalação básica. O extra `documents` instala
PyMuPDF 1.26.6 para extração documental; a dependência de build também está
fixada no `pyproject.toml`.

Consulte [extração documental](../../docs/desenvolvimento/extracao-documental.md)
para instalação, execução, contrato do relatório e limites da limpeza.

Consulte [o guia do ambiente](../../docs/desenvolvimento/ambiente.md).

Consulte [chunking documental](../../docs/desenvolvimento/chunking-documental.md)
para segmentar relatórios de extração com metadados reproduzíveis.

Consulte [índice vetorial educativo](../../docs/desenvolvimento/indice-vetorial.md)
para instalar o extra `vector` e reconstruir coleções Chroma a partir do catálogo.

Consulte [recuperação documental](../../docs/desenvolvimento/recuperacao-documental.md)
para consultar uma coleção e obter evidências com proveniência e score.

O [guia do pipeline RAG](../../docs/desenvolvimento/pipeline-rag.md) reúne
a arquitetura, os parâmetros e a demonstração de ponta a ponta.
