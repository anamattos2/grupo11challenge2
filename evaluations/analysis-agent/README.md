# Avaliação do Analysis Agent

Referência: [S4-03 / #77](https://github.com/anamattos2/grupo11challenge2/issues/77).
Código: `packages/ai/src/finance_ai/agents/avaliacao_analysis.py`; execução:
`scripts/avaliar_analysis.py`. Dados inteiramente fictícios (fixtures).

Pergunta que esta avaliação responde: **a Analysis liga cada afirmação às
evidências, usa só números do backend e diz claramente quando falta dado?**
Cada caso passa pela Research com fixtures e pela Analysis, com a rodada de
cálculo quando ela pede.

## Métricas

| Métrica | Definição | Meta |
|---|---|---|
| `status_correto` | Status final igual ao gabarito | Maior é melhor |
| `pedido_correto` | Pediu (ou não) cálculo ao backend, como esperado | Maior é melhor |
| `lacunas_corretas` | Os códigos de lacuna esperados aparecem | Maior é melhor |
| `valores_corretos` | Os valores esperados aparecem formatados no texto, e os proibidos (outra usuária) não | Maior é melhor |
| `afirmacoes_rastreaveis` | Afirmações que citam evidências existentes e do tipo certo | **Sempre 1,0** |
| `numeros_sem_origem` | Números do texto que não estão nas evidências citadas | **Sempre 0** |
| `rascunhos_recusados` | Rascunhos barrados por `materializar` | Informativo (LLM) |
| `reserva_acionada` | Vezes em que o LLM falhou e as regras assumiram | Informativo (LLM) |

## Baseline (`baseline-regras.json`)

Redator por regras, casos versão 1.0: todas as taxas em 1,0 e zero números
sem origem. Um teste (`tests/test_avaliacao_analysis.py`) falha se o resultado
mudar, e outro roda um redator que inventa números para mostrar que ele nunca
passa.

Com o LLM local: `python scripts/avaliar_analysis.py --redator ollama` (extra
`llm`). O relatório completo vai para `.runtime/avaliacoes/`.
