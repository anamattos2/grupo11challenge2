# Riscos, premissas e métricas de sucesso

Referência: [S1-04 / issue #61](https://github.com/anamattos2/grupo11challenge2/issues/61).
Dependência: [escopo e requisitos / #60](https://github.com/anamattos2/grupo11challenge2/issues/60).
Data: 16/11/2026. Estado: proposta para revisão da equipe.

Este documento define riscos técnicos, medidas preventivas e como avaliar a
entrega. Não contém métricas já medidas nem resultados de pesquisa com usuárias.
Seu fechamento depende da revisão e do alinhamento com a versão aprovada da #60.

## 1. Premissas e limites

| ID | Premissa de planejamento | Consequência e como conferir |
|---|---|---|
| P01 | O público escolhido são mulheres em início de carreira | Personas são referências fictícias; não apresentar necessidades como achados de entrevistas |
| P02 | O desafio avalia implementação e qualidade técnica | Evidências são testes, execuções e documentação; não inferir adesão de mercado ou melhora financeira real |
| P03 | Dados financeiros são autodeclarados | Identificar a origem na interface; exemplos de PDFs não são patrimônio pessoal; não há verificação bancária |
| P04 | Cálculos e autorização pertencem ao backend | Agentes usam ferramentas autorizadas e resultados determinísticos; modelo não recebe SQL livre ou credenciais |
| P05 | O corpus é educativo e curado | Pelo menos 20 fontes únicas têm origem e condições de uso verificáveis; comprovantes pessoais não entram no índice |
| P06 | Texto e imagem são as modalidades de interação do MVP | Imagem gera prévia editável; dados extraídos só viram despesa após confirmação explícita |
| P07 | Modelos e recursos disponíveis ainda precisam ser selecionados | Comparar configurações com dataset identificado; registrar timeout e modo de execução antes da integração |
| P08 | Resultados antigos são material de referência | Preservar experimentos e reavaliar sua reprodução, sem atribuir sucesso ao produto por sua existência |
| P09 | Há quatro agentes e um orquestrador distinto | Rastro deve mostrar Research, Analysis, Validation e Communication; coordenação não substitui nenhum papel |

Premissas técnicas devem ser confirmadas pela equipe e convertidas em testes
nas issues correspondentes. Se uma premissa mudar, atualizar requisitos,
cenários e este registro com justificativa no PR.

## 2. Registro de riscos

Impacto e probabilidade abaixo são estimativas qualitativas da equipe para
planejamento, não frequências observadas. "A avaliar" evita atribuir uma
probabilidade sem evidências. Responsáveis são frentes técnicas; nomes devem
ser atribuídos nas issues de implementação.

| ID | Evento e consequência | Impacto / probabilidade | Mitigação proposta | Evidência de controle | Frente |
|---|---|---|---|---|---|
| R01 | Acesso cruzado expõe ou altera dados de outra usuária | Crítico / a avaliar | Autorizar no backend por sessão e objeto; não confiar em identidade do prompt | Testes com duas usuárias em leitura, escrita, histórico, upload e ferramentas; nenhuma violação | Backend + qualidade |
| R02 | Resposta inventada ou citação sem suporte induz interpretação errada | Alto / a avaliar | RAG rastreável, validação de alegações e abstenção; documentos são dados, não instruções | Gabarito, avaliação humana por afirmação e checagem das citações; casos fora de escopo | RAG + IA + avaliação |
| R03 | LLM calcula errado ou usa período incompleto para a reserva | Alto / a avaliar | Cálculos decimais no backend, período explícito e tratamento de dados insuficientes | Casos com valores conhecidos, meta zero, arredondamento e dados ausentes | Backend + qualidade |
| R04 | OCR registra valor ambíguo ou grava sem confirmação | Alto / a avaliar | Prévia editável, campos ausentes sinalizados e confirmação autorizada | Testes provam zero despesa antes da confirmação e cancelamento sem persistência | Imagens + backend |
| R05 | Reenvio ou concorrência duplica uma despesa | Alto / a avaliar | Idempotência e controle transacional da confirmação | Repetições e confirmações concorrentes geram uma despesa por prévia confirmada | Backend + qualidade |
| R06 | Prompt malicioso tenta obter acesso ou executar ação indevida | Crítico / a avaliar | Ferramentas permitidas, parâmetros tipados e autorização determinística; contexto documental não concede privilégios | Casos adversariais em pergunta, documento e OCR; nenhum acesso ou escrita indevida | IA + backend |
| R07 | Logs, memória, cache ou imagens vazam conteúdo pessoal | Crítico / a avaliar | Minimização, logs sanitizados, isolamento, retenção e limpeza no logout | Inspeção de logs, teste de troca de sessão e expiração; dados sensíveis não aparecem fora do contexto autorizado | Backend + frontend + operação |
| R08 | Modelo, índice ou rede indisponível interrompe o fluxo | Alto / a avaliar | Timeout configurado, estados de erro e interrupção segura da etapa dependente | Falhas induzidas com log correlacionado e ausência de mutação indevida | Integração + IA |
| R09 | Reorganização perde fontes, resultados ou estado necessário à reprodução | Alto / a avaliar | Inventário, mapa de migração e reconstrução antes de retirar índices do Git | Verificador do legado, revisão de hashes e reconstrução em ambiente limpo | RAG + integração |
| R10 | Avaliação enviesada apresenta taxa de sucesso artificial | Alto / a avaliar | Perguntas únicas, protocolo fixado, denominadores e falhas reportados; separar calibração da avaliação | Auditoria de duplicatas, fontes ausentes, exclusões e identificação de revisores | Avaliação |
| R11 | Escopo amplo impede demonstrar requisitos semanais | Alto / a avaliar | Priorizar P0, PRs pequenos e integração contínua; manter melhorias fora do caminho crítico | Matriz de entregáveis com evidências e pendências reais | Equipe |

Controles descritos são propostas, não garantias de que os riscos foram
eliminados. Após implementar, registrar execução, resultado, versão e falhas
residuais. Falha crítica de isolamento, autorização ou gravação exige correção
antes de disponibilizar o fluxo, sem compensação por médias de qualidade da IA.

## 3. Protocolo de medição

Antes da avaliação, fixar dataset, critérios de classificação, corpus,
configuração e conjunto de casos. Registrar commit, modelo, parâmetros, prompt,
embeddings, chunking, data e ambiente. Dados pessoais devem ser fictícios.

Para comparação, usar as mesmas perguntas nas variantes obrigatórias: LLM puro,
LLM + RAG e LLM + RAG com explicação estruturada. Multi-Query e busca híbrida
podem ser variantes adicionais; não substituem a explicação estruturada.

Separar qualidade da recuperação, qualidade da resposta e segurança/integridade.
Casos fora do corpus continuam no relatório: avaliar abstenção e informar a
falha de cobertura. Pergunta repetida não aumenta a contagem de casos únicos.
Se houver várias execuções por pergunta, apresentar os resultados por execução
e a agregação escolhida, sem tratá-las como novas perguntas independentes.

## 4. Métricas previstas

Cada taxa deve ser publicada com numerador, denominador e tamanho do conjunto.
Denominador zero produz "não aplicável", nunca 0% ou 100% por conveniência.
As metas desta tabela são propostas de aceite técnico a revisar, não resultados.

| ID | Métrica e cálculo | Método / unidade de análise | Meta ou decisão de aceite proposta |
|---|---|---|---|
| M01 | Cobertura documental: número de fontes únicas verificáveis; cobertura das perguntas = perguntas com fonte relevante no corpus / perguntas que exigem fonte | Deduplicar por conteúdo, auditar catálogo e mapear gabarito ao corpus | Pelo menos 20 fontes únicas; reportar separadamente lacunas do dataset |
| M02 | Hit@k = perguntas com pelo menos um trecho relevante no top-k / perguntas de recuperação avaliadas | Gabarito define relevância; fixar k e apresentar também o subconjunto com fonte disponível | Medir baseline; limiar de seleção final deve ser definido antes da comparação final |
| M03 | Correção integral = respostas integralmente corretas / execuções de perguntas respondíveis previstas | Revisão humana com rubrica: correta, parcial, incorreta, recusa indevida ou falha técnica; todas entram no denominador | Reportar todas as classes; meta de qualidade final pendente de aprovação prévia |
| M04 | Alucinação = respostas com ao menos uma afirmação factual sem suporte / respostas geradas avaliadas | Avaliar suporte nas evidências RAG; para LLM puro usar gabarito/fontes de referência; não penalizar resultado pessoal autorizado como ausência de fonte documental | Reportar taxa e exemplos; erros críticos não podem ser ocultados na média |
| M05 | Fidelidade de citação = pares afirmação–citação existentes que sustentam a afirmação / pares afirmação–citação avaliados | Revisor verifica existência, localização e suporte; citação inexistente permanece no denominador como falha | Medir por variante; não contar apenas presença visual de referência |
| M06 | Cobertura de suporte = afirmações factuais que requerem evidência e têm suporte identificável / afirmações factuais que requerem evidência | Auditar afirmações, incluindo as sem citação; origem pessoal pode ser ferramenta autorizada | Complementa M05 para impedir taxa artificialmente alta ao omitir citações |
| M07 | Abstenção adequada = execuções de perguntas sem suporte que se abstêm sem inventar / execuções previstas de perguntas sem suporte | Classificar abstenção por conteúdo; falha técnica não conta como abstenção correta; medir recusas indevidas separadamente | Reportar taxa e contagens, inclusive falhas; limiar final a definir antes da avaliação final |
| M08 | Isolamento = tentativas sem acesso cruzado / tentativas de acesso cruzado executadas | Duas usuárias; leitura, escrita, histórico, upload e ferramentas; registrar casos planejados e executados | 100% dos casos executados bloqueados, zero violações; casos críticos planejados não podem ficar sem execução |
| M09 | Exatidão determinística = casos com resultado esperado / casos de cálculo executados | Valores decimais conhecidos, meta zero, dados insuficientes, período e regras aprovadas de arredondamento | 100% nos casos executados; falha de cálculo bloqueia aceite do fluxo |
| M10 | Extração por campo = valores corretamente extraídos / imagens cujo campo tem gabarito legível | Medir valor, data e estabelecimento separadamente; fixar normalização antes do teste; informar total recebido, ilegíveis, ausentes e falhas | Reportar taxas por campo e exemplos; limiar final a definir antes do teste final |
| M11 | Confirmação e idempotência = cenários com persistência esperada / cenários executados de confirmação, cancelamento, repetição e concorrência | Conferir banco antes/depois; zero registro antes de confirmação e um após confirmação válida | 100% dos cenários críticos executados; nenhuma gravação sem confirmação nem duplicação |
| M12 | Falha segura = falhas induzidas com estado seguro e log sanitizado / falhas induzidas executadas | Interromper LLM, vetor, OCR e ferramentas; verificar erro compreensível, correlação e integridade | 100% dos casos críticos executados; registrar serviços e falhas ainda não testados |
| M13 | Latência por cenário: mediana e p95 das durações ponta a ponta | Contar execuções totais, sucessos, erros e timeouts; separar sucesso/erro; com amostra pequena, publicar valores individuais e método do percentil | Sem SLA definido; comparar no mesmo ambiente e registrar timeouts em vez de descartá-los |
| M14 | Rastreabilidade de entrega = requisitos com evidência revisada e vinculada / requisitos P0 aprovados aplicáveis ao marco | Checklist liga requisito, teste/artefato, versão e revisão; requisito descrito sem evidência não conta como atendido | 100% dos P0 do marco final; pendências explícitas impedem alegar entrega integral |

M03 mede a proporção de respostas totalmente corretas e não transforma respostas
parciais em corretas. M04 pode ser baixa quando o sistema se recusa demais;
por isso deve ser lida junto de M03 e M07. M05 não mede a omissão de referências;
M06 cobre essa limitação. Zero violações em um conjunto finito não prova
segurança universal; reportar os casos e os limites de cobertura.

## 5. Revisão humana e registro dos resultados

Uma pessoa avalia com rubrica e outra revisa classificações divergentes ou
duvidosas. Registrar avaliadores, decisão final e justificativa, especialmente
em afirmações sem suporte ou citações parcialmente pertinentes. Sem segunda
revisão, identificar explicitamente o resultado como avaliação preliminar.

Um avaliador automático pode apoiar a triagem, mas suas notas não equivalem
automaticamente a validação humana. Não usar o mesmo conjunto para ajustar
parâmetros e alegar desempenho independente sem declarar essa limitação.

Cada relatório deve conter:

1. Identificação da execução e versões de código, corpus e configuração.
2. Dataset e casos planejados, executados, falhos e não executados.
3. Contagens e taxas, regra de agregação e denominadores.
4. Falhas, exemplos, divergências de revisão e limitações.
5. Evidência sanitizada e link para a tarefa ou PR correspondente.

Modelo mínimo para uma linha de resultado:

| Execução | Métrica | Numerador | Denominador | Resultado | Configuração / evidência | Revisão |
|---|---|---|---|---|---|---|
| A preencher após teste | Mxx | A medir | A medir | Não medido | Vincular versão, dataset e saída | Identificar avaliadores |

Não preencher percentuais antes de executar e revisar a avaliação. Demonstrações
com dados fictícios não medem retenção, adesão, aumento de poupança ou mudança
real de comportamento financeiro.

## 6. Pendências e critério de conclusão

Antes das avaliações finais, a equipe precisa aprovar: tamanhos e composição
dos conjuntos, k da recuperação, rubrica de correção, regras de normalização de
OCR, limites operacionais e metas de qualidade ainda não fixadas. Documentar
essas escolhas nas issues de avaliação e implementação antes de medir a versão
final, para evitar ajustar critérios retrospectivamente aos resultados.

Responsáveis nominais e revisores serão definidos nas issues. Enquanto um
controle não for implementado e testado, seu risco permanece aberto.

| Critério da #61 | Evidência neste documento |
|---|---|
| Riscos de isolamento, alucinação, cálculos e confirmação registrados | R01–R05, com consequências, controles e evidências |
| Premissas e medidas de mitigação definidas | Seção 1 e matriz R01–R11 |
| Métricas com método e denominador previstos | M01–M14 e protocolo de revisão/registro |

Esta issue entrega o plano de controle e medição, não a execução dos testes.
O fechamento exige revisão do documento e integração do PR. O conteúdo será
insumo do pacote de definição de 3 a 5 páginas na #62.

## 7. Referências

- [Issue #61](https://github.com/anamattos2/grupo11challenge2/issues/61) e
  [requisitos da #60](https://github.com/anamattos2/grupo11challenge2/issues/60).
- [Cenário e problema](cenario-problema.md).
- [Arquitetura inicial](../arquitetura/arquitetura-inicial.md).
- PRD v1.1 do Desafio 02, Grupo 11, de 16/11/2026, e cronograma semanal
  fornecidos pela equipe na conversa. Os arquivos originais não estão
  versionados nesta base.
