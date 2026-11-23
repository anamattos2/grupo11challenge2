# Revisão assistida dos 12 casos oficiais da #73

Avaliador: Codex. Data: 23/11/2026. Escopo: as 36 saídas entregues ou
abstenções da rodada oficial, registrada no commit
`b402ebfa130f3b89d7aef50c0291356dc6ffcb2f`. Julgamento pelo gabarito v1.0.0
e pela regra estrita aprovada para pedidos fora de escopo. A revisão humana
dos resultados permanece pendente.

## Resultado por caso

Para aprovar um caso respondível, todos os critérios do gabarito precisam
ser satisfeitos. No RAG, a evidência citada também precisa sustentar a
resposta. Para dados insuficientes, é preciso identificar o dado faltante
sem concluir por suposição. Para fora de escopo, é preciso declarar o
limite e encerrar. Foram julgadas as respostas efetivamente entregues.

| Caso | LLM puro | RAG comum | RAG estruturado |
| --- | --- | --- | --- |
| AVA-01 | Parcial. Dá exemplos de entradas e saídas, mas não explica a comparação entre receitas e despesas no fechamento do mês. | Recusa indevida. A saída foi substituída por abstenção por citações inválidas. | Parcial. Define e exemplifica o registro das operações, mas não explica a comparação mensal. |
| AVA-02 | Correto. Identifica que categorias fixas podem omitir circunstâncias individuais e imprevistos que afetam a família. | Recusa indevida. Pede dados específicos que a pergunta conceitual não exige, embora o trecho citado recomende adaptar as categorias. | Incorreto. Lista exemplos e define custos fixos sem explicar o limite de categorias predefinidas. |
| AVA-03 | Correto. Inclui a matrícula anual no planejamento apesar da frequência anual. | Incorreto. Exclui a matrícula por ser sazonal, contrariando a evidência citada. | Parcial. Menciona gastos avulsos dentro do mês. Não inclui explicitamente a matrícula nem explica a frequência anual. |
| AVA-04 | Parcial. Distingue financiamento de dinheiro próprio, mas omite obrigação de pagamento ou custo. | Recusa indevida. A saída foi substituída por abstenção por citações inválidas. | Incorreto. Reproduz um fragmento sobre receitas e despesas sem distinguir o crédito nem mencionar obrigação ou custo. |
| AVA-05 | Incorreto. Indica taxa nominal e um índice sem suporte no gabarito. O indicador esperado é o CET. | Correto. Identifica o CET, com referência que sustenta a comparação. | Incorreto. A frase trata de alfabetização financeira e juros, sem identificar o CET. |
| AVA-06 | Incorreto. Recomenda contar apenas despesas previsíveis e omite imprevistos. | Parcial por suporte. A recomendação atende ao conteúdo do gabarito, mas a referência escolhida não sustenta a recomendação sobre imprevistos. | Incorreto. Fala em orçar uma festa e contabilizar renda extra, sem orientar sobre imprevistos no acampamento. |
| AVA-07 | Parcial. Relaciona a distinção à priorização de compras, mas não considera o impacto futuro. | Parcial. A fonte sustenta evitar a influência publicitária, mas a resposta não explica a distinção nem os efeitos futuros. | Recusa indevida. O executor se absteve porque nenhuma frase foi selecionada. |
| AVA-08 | Parcial. Identifica orçamento, compromissos e renda para o diagnóstico, sem explicar como dimensionar os recursos disponíveis para a meta. | Parcial. Pede rendimentos e despesas, mas não explica o vínculo com o orçamento e os recursos para a meta. A citação não sustenta a lista completa. | Recusa indevida. O executor se absteve porque nenhuma frase foi selecionada. |
| AVA-09 | Adequado. Pede a renda mensal e não calcula um percentual. | Inadequado. A fórmula é válida, mas a resposta introduz renda hipotética e apresenta 4,5%, sem pedir o valor real do mês. | Inadequado. Reproduz passagens sobre categorias de gastos, sem pedir a renda do mês. |
| AVA-10 | Parcial. Indica somar as parcelas e não escolhe uma proposta, mas não pede os totais ou valores e não considera entrada e cobranças adicionais. | Parcial. Recomenda comparar os valores e não escolhe uma proposta, mas não pede os dados necessários. Renda e despesas pessoais não definem qual proposta tem menor custo total. | Inadequado. Lista exemplos de custos variáveis sem identificar os dados das propostas. |
| AVA-11 | Inadequado pela regra estrita. Declara fora de escopo e não alega acesso, mas pede mais detalhes em vez de encerrar e não explicita a recusa de acesso a dados de terceiros. | Abstenção inadequada. A mensagem genérica não declara a restrição sobre dados bancários de terceiros. | Inadequado. Reproduz um trecho de educação financeira sem declarar a restrição. |
| AVA-12 | Inadequado pela regra estrita. Declara fora de escopo e não confirma compra, mas pede detalhes da viagem em vez de encerrar. | Abstenção inadequada. A mensagem genérica não declara que o serviço não faz reservas ou compras. | Abstenção inadequada. A mensagem informa falta de evidência e não declara o limite de escopo. |

## Contagens pelo gabarito

| Indicador | LLM puro | RAG comum | RAG estruturado |
| --- | ---: | ---: | ---: |
| Aprovação integral | 3/12 | 1/12 | 0/12 |
| M03 · Correção integral nos casos respondíveis | 2/8 | 1/8 | 0/8 |
| Informação insuficiente tratada adequadamente | 1/2 | 0/2 | 0/2 |
| Recusa adequada fora de escopo | 0/2 | 0/2 | 0/2 |
| M07 · Comportamento adequado nos casos sem suporte | 1/4 | 0/4 | 0/4 |
| Abstenções do executor | 0/12 | 4/12 | 3/12 |
| Recusas indevidas em casos respondíveis, incluindo recusas redigidas pelo modelo | 0/8 | 3/8 | 2/8 |
| Falhas técnicas | 0/12 | 0/12 | 0/12 |
| Referências emitidas com localização verificada | N/A | 8/8 | 13/13 |
| M05 · Pares avaliados que sustentam a afirmação associada | N/A | 2/8 | 13/13 (reprodução textual) |

O 13/13 do estruturado mede apoio textual às passagens que o executor
incluiu. Fragmentos e trechos irrelevantes continuam no denominador.
A pertinência à pergunta e o atendimento integral são julgados na tabela
por caso. Em AVA-07, a referência do RAG comum sustenta a afirmação sobre
publicidade, embora essa afirmação seja insuficiente para responder à pergunta.

AVA-08 e AVA-10 ficaram parciais pela leitura estrita dos respectivos
critérios. A primeira resposta do LLM puro oferece um diagnóstico sem
explicitar os recursos disponíveis para a meta. A segunda orienta um
cálculo sem pedir os valores faltantes. Pedir mais detalhes para dar
continuidade à tarefa também foi tratado como falha de encerramento
em AVA-12, embora a resposta cumpra isoladamente os itens de declarar o
limite e evitar confirmação falsa.

## Auditoria das citações

Reextraí com PyMuPDF 1.26.6 os dez PDFs citados. Conferi o SHA-256 das
fontes e a igualdade do texto recuperado com o intervalo da página
física. Para as citações estruturadas, conferi também os offsets da
frase após a normalização dos espaços. No RAG comum, cada referência
distinta emitida foi avaliada em relação à afirmação associada. A
repetição de [1] em AVA-07 aponta para um único par.

| Caso | RAG comum | RAG estruturado |
| --- | --- | --- |
| AVA-01 | Sem referência na resposta entregue. | F018 p. 5, IDs 8 e 9. Ambas as passagens conferem e sustentam a definição e o registro das operações. Nenhuma explica o fechamento mensal. |
| AVA-02 | F001 p. 21. A fonte permite adaptar grupos às necessidades. Não sustenta a alegação de que faltam dados para responder. | F004 p. 5, IDs 11 e 12. Ambos os excertos conferem, mas são exemplos e definição de custos fixos. |
| AVA-03 | F005 p. 7. A fonte inclui matrículas não mensais, contrariando a resposta. | F001 p. 20, ID 4. A passagem confere. Aborda gastos avulsos dentro do mês, sem tratar da matrícula anual. |
| AVA-04 | Sem referência na resposta entregue. | F009 p. 8, ID 12. O fragmento confere. Não trata de recursos de terceiros, pagamento ou juros. |
| AVA-05 | F017 p. 5. Sustenta a comparação por CET. | F022 p. 4, ID 2. A passagem confere, mas menciona juros sem indicar o CET. |
| AVA-06 | F013 p. 9. O trecho fala em planejamento financeiro e renda mensal. Não sustenta a afirmação sobre acampamento e imprevistos. | F017 p. 6, ID 2, e F005 p. 7, ID 4. Ambos conferem. Tratam de orçamento de festa e renda extra anual. |
| AVA-07 | F021 p. 5. Sustenta a afirmação sobre publicidade e consumo irracional. A resposta não cobre todos os critérios da pergunta. | Sem referência na resposta entregue. |
| AVA-08 | F013 p. 9. Menciona renda e objetivos pessoais, sem fundamentar a lista completa de renda e despesas como diagnóstico. | Sem referência na resposta entregue. |
| AVA-09 | F004 p. 5. O trecho é um exemplo de despesas e não sustenta o cálculo com renda hipotética como resposta ao caso. | F015 p. 2, ID 8, e F004 p. 5, ID 14. Ambos conferem. Nenhum identifica a renda faltante. |
| AVA-10 | F004 p. 5. A lista de despesas não sustenta a orientação sobre a comparação das propostas de parcelamento. | F004 p. 5, ID 6. O exemplo confere, sem relação com os valores das propostas. |
| AVA-11 | Sem referência na resposta entregue. | F017 p. 5, ID 7. A passagem confere. Não trata de privacidade ou acesso a contas. |
| AVA-12 | Sem referência na resposta entregue. | Sem referência na resposta entregue. |

Nenhum caso foi excluído. Todas as oito páginas esperadas estavam na
coleção e cinco apareceram no top 5 em cada variante RAG. O RAG comum
respondeu ao conteúdo de AVA-06, mas citou um trecho inadequado. O RAG
estruturado preservou a rastreabilidade das passagens emitidas, mas a
seleção de frases não produziu nenhuma resposta integralmente adequada
nesta rodada. A cobertura de suporte M06 é detalhada abaixo.


## M06 · Cobertura de suporte

A unidade é uma proposição verificável. Afirmações compostas foram
separadas quando suas partes precisavam de evidências diferentes. Contam
conclusões e recomendações factuais, inclusive as sem referência ou
irrelevantes para a pergunta. Excluímos perguntas, pedidos de dados,
mensagens fixas de abstenção e fragmentos sem proposição. Para o LLM
puro, o suporte foi julgado contra o enunciado e o gabarito. Para as
variantes RAG, usamos os trechos efetivamente recuperados, mesmo quando
a resposta citou outro trecho. Também consideramos fatos dados pelo
enunciado e cálculos ou comparações diretamente dedutíveis deles.
Um exemplo condicional matematicamente correto continua sujeito ao
critério do caso sobre apresentar um percentual antes de obter a renda.

| Caso | LLM puro | RAG comum | RAG estruturado |
| --- | --- | --- | --- |
| AVA-01 | 2/3. Os exemplos de entradas e saídas são compatíveis. A conclusão sobre otimização não decorre do gabarito do fechamento mensal. | 0/0. Abstenção. | 2/2. Definição patrimonial e registro das operações. |
| AVA-02 | 1/1. Categorias fixas podem omitir circunstâncias individuais. | 0/1. A suposta necessidade de dados específicos não tem suporte. | 2/2. Exemplos de categorias e periodicidade dos custos fixos. |
| AVA-03 | 1/1. Matrícula anual deve ser incluída. | 0/1. Exclusão de matrícula é contrariada pelo material. | 1/1. Orientação sobre registrar gastos avulsos e disciplinar o planejamento. |
| AVA-04 | 2/2. Crédito é financiamento de terceiros e difere de dinheiro próprio. | 0/0. Abstenção. | 0/0. Fragmento instrucional sem proposição sobre crédito. |
| AVA-05 | 0/1. O índice indicado não substitui o CET. | 1/1. O CET é indicador de comparação. | 1/1. A associação entre alfabetização financeira, dívida, poupança e juros foi reproduzida como uma proposição composta da fonte. |
| AVA-06 | 0/1. Limitar o orçamento a despesas previstas contraria o gabarito. | 2/2. Despesas do acampamento e verba para imprevistos constam em F017 p. 6, embora a resposta cite F013 p. 9. | 1/1. Orientação de contabilizar renda extra anual. A lista de atividades não afirma que as ações ocorreram. |
| AVA-07 | 1/1. Distinguir prioridades ajuda a evitar compras desnecessárias. | 1/1. A recomendação sobre influência publicitária é apoiada pela fonte. | 0/0. Abstenção. |
| AVA-08 | 1/1. Orçamento, compromissos e renda integram o diagnóstico inicial. | 1/2. A renda é sustentada como aspecto do planejamento. A orientação sobre despesas como diagnóstico da meta fica sem suporte suficiente nos trechos recuperados. | 0/0. Abstenção. |
| AVA-09 | 0/0. Pede o dado faltante. | 2/2. Fórmula e resultado condicional de 4,5% são verificáveis por aritmética. O dado de R$ 4 mil foi apresentado como hipótese. | 1/1. Exemplos e definição de custos indiretos são rastreáveis. A pergunta sobre 50% não foi contada como afirmação. |
| AVA-10 | 1/1. Somar parcelas é parte válida da comparação. A omissão de entrada e encargos já afeta a aprovação do caso. | 1/2. Comparar os valores das propostas é pertinente. Vincular o custo relativo à renda e às despesas pessoais não tem suporte. | 1/1. Os exemplos de custos variáveis são rastreáveis. |
| AVA-11 | 0/0. Declaração de escopo e pedido de contexto. | 0/0. Abstenção. | 0/0. Lista de atividades sem proposição material sobre a pergunta. |
| AVA-12 | 0/0. Declaração de escopo e pedido de contexto. | 0/0. Abstenção. | 0/0. Abstenção. |
| **Total** | **9/12** | **8/12** | **9/9** |

A M06 alta no estruturado decorre da reprodução de trechos e pode
coexistir com aprovação zero. Os totais dependem da unidade de
segmentação declarada acima e ficam sujeitos à validação humana.
