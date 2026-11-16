# Cenário, público, problema e Essential Question

Referência: [S1-01 / issue #58](https://github.com/anamattos2/grupo11challenge2/issues/58).
Data: 16/11/2026. Estado: proposta para revisão da equipe.

Este documento compõe a definição do projeto do Desafio 02, Grupo 11, da
Residência em Inteligência Artificial. Registra premissas de contexto e delimita
uma entrega técnica; não apresenta resultados de pesquisa com usuárias.

## 1. Cenário escolhido

O projeto se situa no cenário de qualidade de vida, com foco em organização
financeira e planejamento de uma reserva de emergência. A situação de referência
é o início da vida profissional, quando uma pessoa passa a organizar sua renda,
suas despesas e objetivos financeiros.

A equipe desenvolverá uma aplicação web progressiva (PWA) para reunir registros
financeiros declarados e explicações educativas fundamentadas em documentos.
O recorte permite demonstrar integração entre interface web, regras financeiras,
RAG, quatro agentes e processamento de imagens em fluxos verificáveis.

Organização financeira é o contexto do desafio. Não se assume que a aplicação,
por si só, aumente a renda, reduza desigualdades ou garanta a formação de uma
reserva. Esses efeitos não serão tratados como resultados comprovados.

## 2. Público de referência

O público escolhido é composto por mulheres em início de carreira que desejam
organizar suas finanças e planejar uma reserva de emergência. Para delimitar o
MVP, considera-se uma usuária que registra manualmente receitas e despesas,
consulta sua situação e acompanha uma meta de reserva.

"Início de carreira" é um recorte de trajetória profissional, não uma faixa
etária ou de renda definida nesta etapa. Não se presume vínculo formal de
emprego, estabilidade de renda, escolaridade ou composição familiar específica.
Variações desses perfis serão explicitadas nas personas de referência.

Necessidades assumidas para orientar a implementação:

- Consultar receitas e despesas por período e categoria.
- Identificar despesas essenciais usadas no cálculo da meta de reserva.
- Entender meta, saldo declarado e progresso, com cálculos conferíveis.
- Fazer perguntas sobre os próprios registros e sobre educação financeira,
  distinguindo as duas origens de informação.
- Revisar dados sugeridos a partir de comprovantes antes de registrá-los.
- Identificar as fontes e os limites das explicações produzidas pela IA.

Essas necessidades são hipóteses de trabalho do projeto. Não foram confirmadas
por entrevistas, observação de uso ou teste de adesão. O recorte feminino não
pressupõe menor capacidade financeira nem comportamento de consumo uniforme.

## 3. Problema delimitado

**Como organizar registros financeiros declarados e informações educativas de
modo que uma mulher em início de carreira possa compreender sua situação e
planejar uma reserva de emergência, com cálculos verificáveis e explicações
cujo suporte documental seja identificável?**

Para fins de implementação, o problema se divide em três necessidades:

| Necessidade | Resposta técnica proposta | Limite a preservar |
|---|---|---|
| Organizar os próprios registros | Receitas, despesas, categorias e contas manuais persistidas em PostgreSQL | O sistema conhece apenas o que foi declarado, sem conferir saldo bancário |
| Planejar e acompanhar a reserva | Cálculo determinístico de meta, saldo e progresso no backend | Dados insuficientes devem ser explicitados; o modelo não inventa valores pessoais |
| Entender respostas e orientações | RAG e quatro agentes com evidências, validação e comunicação clara | Fonte educativa não comprova patrimônio pessoal; citação não garante suporte correto sem avaliação |

Não se afirma que ferramentas financeiras existentes sejam inadequadas nem
que esse público não tenha acesso a elas. A proposta estabelece um cenário
demonstrável para o desafio, sem diagnóstico de mercado não realizado.

## 4. Essential Question proposta

> Como uma solução com IA e fontes verificáveis pode apoiar a organização de
> dados financeiros e o planejamento de uma reserva de emergência para mulheres
> em início de carreira?

A formulação segue a proposta do PRD v1.1. Ela orienta a equipe a demonstrar
apoio à organização e ao planejamento, com rastreabilidade das respostas. Não
antecipa eficácia financeira ou adoção do produto.

Na revisão desta issue, a equipe deve confirmar se a pergunta mantém o público,
o problema e o escopo alinhados ao desafio. Alterações devem ficar registradas
no PR. A redação acima é uma proposta; a revisão humana será evidenciada pela
aprovação do PR correspondente, sem alegar aprovação antes que ela ocorra.

## 5. Escopo técnico e validação de mercado

| Dentro da entrega técnica | Fora da avaliação deste desafio |
|---|---|
| Construir e demonstrar interface, persistência e regras financeiras | Comprovar aderência de mercado, adesão ou retenção |
| Recuperar documentos com origem, página e trecho | Afirmar que entrevistas ou personas foram validadas sem pesquisa realizada |
| Executar Research, Analysis, Validation e Communication em fluxo rastreável | Demonstrar melhora de saúde financeira real das usuárias |
| Receber texto e imagem, com prévia editável e confirmação de gravação | Medir aumento de poupança ou efeito causal sobre comportamento |
| Avaliar qualidade, alucinações, citações, erros e isolamento de dados | Prometer que respostas da IA asseguram resultados financeiros |

O produto terá contas e transações manuais, aportes e retiradas autodeclarados.
Movimentação bancária real, Open Finance, sincronização bancária e recomendação
individual de ativos financeiros ficam fora do MVP. A descrição arquitetural
está na [BASE-01](../arquitetura/arquitetura-inicial.md).

## 6. Cenário fictício de demonstração

Uma usuária fictícia registra despesas essenciais de R$ 2.000,00 por mês e
escolhe cobertura de três meses. O backend calcula meta de R$ 6.000,00.
Com saldo declarado de R$ 600,00, o progresso calculado é de 10%.

Ao perguntar como começar a reserva, ela recebe os resultados dos cálculos e
uma explicação educativa com fontes recuperadas. A resposta diferencia seus
registros pessoais dos exemplos presentes nos documentos. Se faltarem dados
ou evidências, a assistente comunica a limitação.

Uma imagem de comprovante pode gerar uma prévia de despesa, mas somente a
confirmação da usuária autoriza sua persistência. Toda a demonstração utiliza
dados fictícios e não representa teste com usuárias reais.

O cenário é especificação do comportamento esperado. Não comprova que as
funcionalidades já estejam implementadas.

## 7. Continuidade e evidências de aceite

| Critério da #58 | Evidência para revisão |
|---|---|
| Problema e contexto descritos | Seções 1–3: cenário, público, necessidades assumidas e problema delimitado |
| Essential Question revisada | Seção 4: redação proposta e justificativa; aprovação ou ajustes registrados no PR |
| Escopo técnico diferenciado de validação de mercado | Seção 5: separação de entregas técnicas e alegações que exigiriam pesquisa adicional |

As próximas tarefas detalham stakeholders e personas (#59), requisitos e
exclusões (#60), riscos e métricas (#61) e consolidam o pacote de definição de
3 a 5 páginas (#62). Este documento não substitui esse pacote nem conclui essas
issues. A #58 poderá ser encerrada após revisão e integração do seu PR.

## 8. Referências de planejamento

- [Issue #58 — Definir cenário, público, problema e Essential Question](https://github.com/anamattos2/grupo11challenge2/issues/58).
- PRD v1.1 e Matriz de Rastreabilidade do Desafio 02, Grupo 11, de 16/11/2026,
  fornecido pela equipe no arquivo `PRD_v1_1_Desafio_02_Grupo11.html`.
- Cronograma de referência fornecido em
  `Cronograma Semanal_Superficial_Tudo_pode_mudar.docx`, semana 1: pacote de
  definição do projeto com cenário, problema e Essential Question, entre outros
  elementos.

As referências locais acima foram fornecidas na conversa; ainda não constituem
arquivos versionados deste repositório. Não foram usados dados externos para
atribuir características ou resultados financeiros ao público de referência.
