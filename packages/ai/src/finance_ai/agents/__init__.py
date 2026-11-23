"""Agentes Research, Analysis, Validation e Communication.

- ``contratos``: modelos de entrada e saída de cada papel (S4-01 / #75).
- ``fluxo``: política de aprovação, abstenção e falha (S4-01 / #75).
- ``grafo``: o fluxo como grafo LangGraph (S4-01 / #75).
- ``research``: Research Agent (S4-02 / #76), subgrafo LangGraph com ferramentas
  LangChain (``ferramentas``), planejador por LLM ou regras (``planejador``) e
  fixtures sintéticas (``fixtures``). O LLM local exige o extra ``llm``
  (``langchain-ollama``).
- ``backend``: adaptador para as ferramentas financeiras reais da BE-06 (#88).

Visão geral curta da pasta: ``README.md``.

Requer o extra ``agents`` (Pydantic, LangChain Core, LangGraph):
``pip install -e './packages/ai[agents]'``.
"""
