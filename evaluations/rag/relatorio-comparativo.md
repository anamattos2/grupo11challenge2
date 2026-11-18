# Relatório comparativo de LLM e RAG

**Semana 3 · Calibração de 18/11/2026 · Revisão humana pendente**

O RAG com explicação estruturada aprovou **2 de 6 casos**, ante **1 de 6**
no LLM puro e **1 de 6** no RAG comum. A explicação estruturada aumentou a
rastreabilidade das afirmações entregues. A busca encontrou a página
esperada nos quatro casos respondíveis nas duas variantes RAG. Algumas
respostas ainda usaram trechos que não resolviam a pergunta.

| Resultado preliminar | LLM puro | RAG | RAG com explicação estruturada |
| --- | ---: | ---: | ---: |
| Aprovação pelo gabarito | 1/6 | 1/6 | 2/6 |
| Correção integral nos casos que exigem evidência | 1/4 | 1/4 | 2/4 |
| Respostas entregues com afirmação material sem suporte | 2/6 | 2/4 | 0/5 |
| Pares afirmação–citação sustentados | N/A | 2/4 | 7/7 |
| Página esperada entre os cinco candidatos | N/A | 4/4 | 4/4 |
| Respostas adequadas a dados faltantes ou fora de escopo | 0/2 | 0/2 | 0/2 |
| Abstenções do executor | 0/6 | 2/6 | 1/6 |
| Falhas técnicas | 0/6 | 0/6 | 0/6 |

A comparação considera as respostas entregues. Os denominadores da
métrica de afirmações sem suporte variam porque as abstenções fixas do
executor não entram nessa contagem. As sete citações fiéis no RAG
estruturado acompanham frases reproduzidas do acervo. Em um caso sobre gasto
pessoal com transporte, a frase citada era rastreável, mas faltavam os
lançamentos da pessoa. O [registro caso a caso](avaliacao-qualidade.md)
detalha o julgamento, as abstenções e as latências.

## Configuração e evidências

- **Dataset e gabarito v1.0.0.** Seis perguntas de calibração, sendo quatro
  com evidência, uma com dados insuficientes e uma fora de escopo. Os
  doze casos oficiais permanecem reservados. [Dataset](dataset.json) · [Gabarito](gabarito.json)
- **Código executado.** Commit `b402ebfa130f3b89d7aef50c0291356dc6ffcb2f`.
  [Baseline](baseline-llm.md) · [RAG](variante-rag.md) · [Explicação estruturada](explicacao-estruturada.md)
- **Ambiente e parâmetros.** Ollama 0.32.5, Qwen2.5 3B Q4_K_M, prompt base
  `direto-v2`, temperatura 0, seed 42, 256 tokens de saída e contexto
  de 2.048 tokens. Os dois RAGs usaram top 5 e limiar 0,85.
- **Acervo.** Coleção acadêmica local de 20 PDFs, com 27 páginas selecionadas
  e 87 trechos. As duas variantes RAG receberam os mesmos trechos. As quatro
  páginas de referência estavam disponíveis. [Catálogo](../../knowledge/catalogo.json)
- **Identificadores e reprodução.** O relatório da #73 registra o digest do
  modelo, o hash do dataset, o nome da coleção e os comandos. Os três JSONL
  brutos ficam em `.runtime/avaliacoes/issue-73/`. [Registro da execução](avaliacao-qualidade.md)

A comparação usa três variantes obrigatórias. A coluna de explicação
estruturada identifica afirmações, evidências e limites por resposta.
Multi-Query pode ser estudado como estratégia adicional de recuperação
em uma comparação futura.

## Limitações e revisão humana

O resultado é de uma execução curta por variante, com seleção de páginas
do acervo e sem a triagem experimental. As contagens não permitem estimar
a qualidade no conjunto oficial. Codex fez a revisão preliminar. A equipe
ainda precisa indicar quem revisará o gabarito, a pertinência das citações
e os casos de abstenção. [PR de calibração](https://github.com/anamattos2/grupo11challenge2/pull/133)

Após resolver as divergências, registre os revisores e congele dataset,
gabarito, código, modelo, prompts e coleção. Execute os 12 casos oficiais
nas três variantes e complemente este relatório com os resultados e
denominadores da avaliação.
