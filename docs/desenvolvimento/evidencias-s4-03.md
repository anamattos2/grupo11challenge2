# Evidências locais — S4-03 / #77

Verificação em 23/11/2026, branch `feat-77-analysis-agent`, criada sobre
`feat-76-research-agent` (S4-02), que por sua vez está sobre
`fix-75-referencias-entre-etapas` (correção da segunda revisão do #135).
Dados inteiramente fictícios. Este registro não substitui revisão e merge do PR.

## O que foi entregue

- `AnalysisAgent` (`analysis.py`) como subgrafo LangGraph
  (`diagnosticar → pedir_calculo | dados_insuficientes | redigir → conferir`).
- Números só por referência (`redacao.py`): o redator escreve marcadores
  `{{id|chave}}` e `materializar` troca pelos valores do backend, recusando
  algarismo digitado, referência quebrada e natureza incoerente.
- Dois redatores: `RedatorPorRegras` (padrão) e `RedatorLLM`
  (`with_structured_output`, Ollama local opcional, regras como reserva).
- `montar_resposta` passa a levar as lacunas de uma análise parcial para
  `RespostaFinal.limites`.
- Avaliação offline com 14 casos e baseline versionada.
- Documentação: `docs/arquitetura/agentes/analysis-agent.md`.

## Critérios de aceite

| Critério | Evidência |
|---|---|
| Análise associa afirmações às evidências | `AfirmacoesLigadasAsEvidenciasTest`; invariantes do `test_analysis_exaustivo.py` (toda afirmação cita evidência existente, do tipo certo para a natureza, sem trecho com instrução); `afirmacoes_rastreaveis = 1,0` na avaliação |
| Cálculos financeiros usam ferramenta e não aritmética livre do LLM | `CalculosPorFerramentaTest` (comparação com mês ausente vira `PedidoCalculo`; número digitado, marcador quebrado e valor nulo são recusados); `RedatorLLMTest` (número inventado pelo modelo nunca chega à saída); `numeros_sem_origem = 0` com redator por regras e com redator adversário |
| Dados insuficientes geram indicação explícita | `DadosInsuficientesTest` (reserva sem cadastro diz o que falta; sem permissão diz isso; período assumido avisa; sem registro essencial e sem trecho relevante viram lacuna; lacuna parcial aparece em `RespostaFinal.limites`; no grafo, vira pedido de complemento) |

## Execução

```text
python -m pip install --editable './packages/ai[documents,agents]'
python scripts/exportar_schemas_agentes.py --check → OK
python -m unittest discover -s tests              → 179 testes OK (2 pulados: Ollama real)
python scripts/avaliar_analysis.py                → status, pedido, lacunas e valores 1,0; números sem origem 0
```

Exemplo (`python -m finance_ai.agents.analysis "Gastei mais em outubro ou em setembro?"`):

```text
Research: concluida (1 evidências)           ← trouxe só setembro
Analysis pediu cálculo: c1 resumo_transacoes 2026-10-01..2026-10-31
a1  dado_pessoal  Em outubro de 2026 você registrou R$ 1.930,40 em despesas.
a2  dado_pessoal  Não há despesas registradas em setembro de 2026.
a3  calculo       Suas despesas em outubro de 2026 (R$ 1.930,40) foram maiores que em setembro de 2026 (R$ 0,00).
```

## Testes exaustivos e prova de que pegam erro

`tests/test_analysis_exaustivo.py` combina 14 perguntas, 2 usuárias, 3
conjuntos de permissão, fonte financeira e índice documental funcionando ou
fora do ar, e 8 redatores: regras e sete comportamentos de LLM (fiel, digita
número, id fantasma, natureza trocada, exceção, vazio, saída quebrada). Inclui
a rodada de cálculo e uma revisão com feedback. São mais de 1.800 execuções em
cerca de 6 s.

Cada defesa foi quebrada de propósito para ver o teste falhar:

| Defesa removida | Resultado |
|---|---|
| Descartar trecho com instrução | Falha: afirmação cita `SYN003` |
| Orientação educativa não pode citar dado financeiro | Falha |
| Algarismo fora de marcador + checagem final `numeros_conferem` (as duas camadas) | Falha |
| Não responder só a parte conceitual (roteamento + conferência, as duas camadas) | Falha: `analisada` sem dado pessoal |

Com só uma das camadas removida, a outra segura e o teste continua passando,
o que é esperado da defesa em profundidade.

## Limites

- Comparação diz "maiores/menores/iguais"; a diferença em reais depende de uma
  nova operação no backend.
- Palavra comparativa escrita por LLM ("o dobro") não tem algarismo e não é
  barrada por regra; fica para a Validation (S4-04).
- A comparação LLM × regras com o Ollama não foi executada neste ambiente.
