# Pacote de IA

Base instalável para RAG, quatro agentes, orquestração e processamento de imagens.
Inclui extração e limpeza local de texto de PDFs com rastreabilidade por página.
Os contratos dos quatro agentes e a política de fluxo (aprovação, abstenção e
falha) ficam em `finance_ai.agents` e exigem o extra `agents` (Pydantic,
LangChain Core e LangGraph).
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

Consulte [contratos dos agentes](../../docs/arquitetura/agentes/contratos-agentes.md)
para papéis, schemas, exemplos e fluxo.
