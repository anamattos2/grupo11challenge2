# Agentes: o que está acontecendo aqui

Esta pasta guarda a camada de IA que responde às perguntas da usuária no chat.
Uma pergunta passa por quatro agentes, cada um com um papel só:

```
pergunta → Research → Analysis → Validation → Communication → resposta
           (busca)    (conclui)  (confere)    (redige)
```

- **Research** busca evidências: trechos do corpus educativo e números dos
  registros financeiros da própria usuária. Não interpreta nada.
- **Analysis** transforma evidências em afirmações curtas, cada uma ligada às
  evidências que a sustentam. Se faltar um número, pede um cálculo ao backend.
- **Validation** confere se cada afirmação está sustentada. Se não estiver, a
  resposta não sai.
- **Communication** escreve a resposta em português usando só o que foi aprovado.

Quando não há base para responder, o sistema diz isso. Ele não inventa uma
resposta.

## Onde está cada coisa

| Arquivo | O que faz | Issue |
|---|---|---|
| `contratos.py` | Formato exato de entrada e saída de cada agente (Pydantic) | S4-01 / #75 |
| `fluxo.py` | Regras de aprovação, abstenção e falha, em funções puras | S4-01 / #75 |
| `grafo.py` | O mesmo fluxo montado no LangGraph | S4-01 / #75 |
| `research.py`, `planejador.py`, `ferramentas.py` | Research Agent: planeja, chama ferramentas, devolve evidências | S4-02 / #76 |
| `backend.py` | Liga a Research às ferramentas financeiras reais do backend | S4-02 / #76 + BE-06 / #88 |
| `fixtures.py`, `fixtures/` | Dados fictícios para desenvolver e testar sem banco | S4-02 / #76 |
| `avaliacao.py` | Mede se o planejador escolhe as ferramentas certas | S4-02 / #76 |

Analysis, Validation e Communication ainda não estão implementados; os
contratos deles já existem, e o fluxo é testado com agentes falsos.

## Protótipo ou real?

Toda evidência diz de onde veio (`origem.sintetica`), e toda pesquisa diz se
usou alguma fixture (`modo = "prototipo_fixtures"` ou `"integrado"`). Hoje:

| Peça | Fixture | Real |
|---|---|---|
| Busca no corpus | `RetrieverFixture` (por palavras) | `RetrieverChroma`, pronto, espera o merge da #67 |
| Dados financeiros | `ConsultaFinanceiraFixture` | `FonteFinanceiraBackend`, pronto, testado contra a BE-06 (#88) |
| Planejamento | `PlanejadorPorRegras` | `PlanejadorLLM` com Ollama local (opcional) |

A fixture financeira segue as mesmas regras da BE-06. Um teste confere que,
para os mesmos dados, as duas produzem a mesma evidência.

## Segurança em uma frase

O modelo nunca escolhe de quem são os dados: a usuária vem da sessão, entra
pelo código, fica fora do que o modelo vê, e cada ferramenta confere de novo.

## Para rodar

```bash
python -m pip install --editable './packages/ai[documents,agents]'
python -m finance_ai.agents.research "Quanto gastei com despesas essenciais em outubro?"
python -m unittest discover -s tests
python scripts/avaliar_research.py
```

Documentação completa:
[contratos e fluxo](../../../../../docs/arquitetura/agentes/contratos-agentes.md) ·
[Research Agent](../../../../../docs/arquitetura/agentes/research-agent.md) ·
[avaliação](../../../../../evaluations/research-agent/README.md).
