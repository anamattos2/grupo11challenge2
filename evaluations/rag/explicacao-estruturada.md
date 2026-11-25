# RAG com explicação estruturada

Esta variante usa os mesmos candidatos, modelo e parâmetros do
[RAG comum](variante-rag.md). A instrução pede que o modelo escolha até dois IDs de frases do contexto
e liste as informações faltantes. O programa monta as afirmações a partir
das frases originais. O comando padrão usa a partição de calibração.

```bash
python -m finance_ai.llm_rag_explained \
  --db .runtime/chroma-academico-local --collection "$COLECAO"
```

Para comparar as variantes, use a mesma coleção, digest do modelo, prompt
base, limiar e limite de recuperação. O cabeçalho JSONL também registra a
instrução e o esquema JSON pedidos ao modelo. Os relatórios ficam em
`.runtime/avaliacoes/`.

## Contrato da explicação

| Campo | Conteúdo |
| --- | --- |
| `response` | Resposta composta pelas afirmações confirmadas ou uma abstenção. |
| `evidence` | Trechos recuperados com texto, documento, página, offsets e score. |
| `sentence_candidates` | Frases numeradas enviadas ao modelo e suas localizações. |
| `explanation.claims` | Frase selecionada, ID, estado de suporte e motivo de rejeição quando aplicável. Uma afirmação confirmada inclui ID do trecho, documento, SHA-256 da fonte, página e offsets da frase. |
| `explanation.missing_information` | Informações faltantes indicadas na geração, separadas da resposta factual. |
| `explanation.limits` | Motivo da abstenção ou aviso de que houve afirmações descartadas. |
| `raw_response` | Saída original para auditoria. |

A lista de candidatos usa pontuação e os limites observáveis dos chunks.
O começo de um chunk intermediário é descartado até o primeiro fim de
frase e a cauda sem pontuação final fica fora da lista. Páginas podem
começar no meio de um parágrafo, e cabeçalhos extraídos podem aparecer
junto do texto. O programa descarta IDs desconhecidos e se abstém quando
não há candidatos ou seleção válida. As citações são preenchidas a partir
do contexto, com offsets inclusivo e exclusivo no texto limpo da página.

Um ID válido garante rastreabilidade textual. A pertinência da frase para
a pergunta e a correção da resposta continuam sujeitas ao
[gabarito e à revisão humana](README.md).

## Verificação

```bash
python -m unittest discover -s tests -p 'test_llm_rag_explained.py'
```

Os testes usam evidência fictícia para verificar localização, descarte de
afirmações sem suporte, informação faltante, abstenção e saída inválida.

## Calibração com o acervo original

Use a coleção dos 20 PDFs selecionados para o protótipo acadêmico local.
O [PR de reconstrução do acervo](https://github.com/anamattos2/grupo11challenge2/pull/120)
documenta como gerar a coleção. Na raiz do repositório:

```bash
COLECAO=$(python -c 'import json; print(json.load(open(".runtime/indice-academico-local.json"))["collection"])')
python -m finance_ai.llm_rag_explained --model qwen2.5:3b \
  --db .runtime/chroma-academico-local --collection "$COLECAO" \
  --output-dir .runtime/avaliacoes/acervo-20
```

A execução usa os seis casos de calibração e a coleção acadêmica com 87
trechos distribuídos por 27 páginas selecionadas dos 20 PDFs. Os trechos
recuperados e as saídas brutas permanecem no relatório local.

Na calibração local com Qwen2.5 3B, a página indicada no gabarito apareceu
entre os cinco candidatos nos quatro casos com evidência. Ao trocar a
cópia literal pela seleção por ID, as respostas com referência válida
passaram de zero para cinco, com uma abstenção e zero erros técnicos.
Todos os offsets retornados foram conferidos contra o texto limpo dos
PDFs. A revisão preliminar aprovou dois casos pelo gabarito. Em uma
pergunta sobre gasto pessoal, o modelo escolheu trechos genéricos em vez
de pedir os lançamentos necessários. Os casos oficiais seguem reservados.
