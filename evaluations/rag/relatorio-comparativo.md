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

## Entregas e rastreabilidade

| Entrega | O que ficou disponível |
| --- | --- |
| Catálogo, extração e chunking | Inventário de 20 PDFs identificados, extração por página e janelas com IDs reproduzíveis. [Catálogo](../../knowledge/catalogo.json) · [Extração](../../docs/desenvolvimento/extracao-documental.md) · [Chunking](../../docs/desenvolvimento/chunking-documental.md) |
| Embeddings, Chroma e reconstrução local | E5 Small com revisão fixada, persistência sem duplicatas e comando para cada colega reconstruir a seleção acadêmica. [Índice](../../docs/desenvolvimento/indice-vetorial.md) · [PR de reconstrução do acervo](https://github.com/anamattos2/grupo11challenge2/pull/120) |
| Busca e demonstração | Evidências com documento, página, offsets e score. A demonstração inicial usou PDFs fictícios. A calibração com o acervo usou os 20 PDFs originais. [Recuperação](../../docs/desenvolvimento/recuperacao-documental.md) · [Guia do pipeline](https://github.com/anamattos2/grupo11challenge2/pull/124) |
| Dataset e três executores | 18 perguntas únicas com gabarito separado, 6 para calibração e 12 para avaliação. Os executores registram configurações, respostas, falhas e latências em JSONL. [Dataset e protocolo](README.md) · [PR do dataset](https://github.com/anamattos2/grupo11challenge2/pull/125) |

## Experimentos complementares

As observações abaixo são de calibração. A tabela principal compara as
três variantes sob uma configuração comum. Os experimentos seguintes
incluem mudanças de prompt, modelo, seleção de trechos e triagem. Os
números são comparáveis dentro de cada linha, nas condições indicadas.

| Experimento | Resultado observado | O que aprendemos |
| --- | --- | --- |
| Prompt original e direto no LLM puro, Qwen2.5 0,5B | Aprovação de 0/6 para 1/6. Cortes de 2/6 para 0/6. | O prompt mais direto reduziu cortes. Erros de orçamento e fluxo de caixa persistiram. |
| LLM puro com 0,5B e 3B, mesmo prompt direto | Ambos aprovaram 1/6. Latência mediana de 514 ms e 1.195 ms, respectivamente. | O aumento de tamanho, isolado, não elevou a aprovação nesta rodada. |
| LLM puro e primeiro RAG com 0,5B | Aprovação de 1/6 e 0/6, respectivamente. O RAG recuperou a página esperada em 4/4 casos com evidência. | Encontrar a página certa ainda permitiu erros de geração e uso de um valor de exemplo como se fosse pessoal. |
| Cinco trechos em texto livre e dois trechos com resposta estruturada | A página esperada caiu de 4/4 para 2/4. Ambas as configurações aprovaram 0/6. Quatro das cinco saídas estruturadas foram rejeitadas. | O teste mudou dois fatores ao mesmo tempo. |
| Reordenação dos cinco candidatos e envio de até três páginas distintas | A página esperada entre os trechos enviados caiu de 4/4 para 3/4. Ambas aprovaram 0/6. | A seleção perdeu a página sobre revisão de metas. |
| Triagem separada que gera classe e texto | Após validação, os modelos 0,5B e 3B acertaram 1/6 rotas cada. Nenhuma pergunta chegou ao gerador RAG. | O 0,5B concentrou tudo em dados insuficientes. O 3B acertou 4/6 rótulos brutos, mas misturou classe e texto. |
| Triagem 3B com rótulo único e prompt revisado | A saída só com rótulo elevou as rotas válidas e corretas de 1/6 para 4/6. O prompt revisado chegou a 6/6 e acertou 6/6 em uma sondagem separada. | Explicitar a diferença entre orientação educativa e execução reduziu os bloqueios indevidos. |
| Prompt de geração fundamentada e troca do gerador 0,5B pelo 3B | O prompt mais curto manteve 0/4 nas perguntas educativas. A troca pelo 3B também manteve 0/4, com cortes de 2/4 para 0/4. | Citações numericamente válidas ainda podiam apontar para outra fonte ou para um trecho sem suporte à conclusão. |
| Explicação estruturada com cópia de frase e depois seleção por ID | No acervo original, a cópia literal produziu seis abstenções. A seleção por ID passou a entregar cinco respostas rastreáveis e aprovou 2/6. | Conferimos os offsets das sete frases selecionadas no texto dos PDFs. A pertinência continuou sendo avaliada pelo gabarito. |
| Triagem revisada combinada com seleção por ID | Aprovação de 2/6 para 4/6, com 6/6 rotas corretas. | O sistema pediu os lançamentos de transporte e declarou o conserto fora de escopo. As quatro respostas educativas ficaram iguais. |

O experimento combinado usou o mesmo acervo acadêmico e as mesmas seis
perguntas. A triagem continua experimental. A mensagem de esclarecimento
foi avaliada apenas para um gasto por categoria e período. O índice, as
saídas e os trechos recuperados permanecem em `.runtime/avaliacoes/` e
`.runtime/chroma-academico-local/`.

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
