# Pacote de definição do projeto

## 1. Cenário, problema e Essential Question

Residência em Inteligência Artificial · Desafio 02 · Grupo 11
Versão 0.1 · 16/11/2026 · Proposta para revisão · Issue #62

### Contexto e público

No cenário de qualidade de vida, o projeto aborda organização financeira e planejamento de reserva de emergência para mulheres em início de carreira. O início da trajetória profissional é um recorte de contexto, sem faixa etária, renda, vínculo empregatício ou composição familiar presumidos.

A proposta é uma aplicação web progressiva (PWA) que reúne registros financeiros declarados e explicações educativas fundamentadas em documentos. As necessidades do público são premissas de projeto, não resultados de entrevistas ou validação de mercado. O recorte não pressupõe menor capacidade financeira nem hábitos uniformes de consumo.

### Problema delimitado

Como organizar registros financeiros declarados e informações educativas de modo que uma mulher em início de carreira compreenda sua situação e planeje uma reserva de emergência, com cálculos verificáveis e suporte documental identificável?

O desafio técnico é separar três origens: dados pessoais registrados no sistema, conhecimento educativo recuperado de documentos e texto gerado pelo modelo. Um exemplo de PDF não pode se tornar saldo pessoal, e uma resposta convincente não substitui cálculo ou autorização do backend.

### Essential Question

Como uma solução com IA e fontes verificáveis pode apoiar a organização de dados financeiros e o planejamento de uma reserva de emergência para mulheres em início de carreira?

### Objetivo e cenário de demonstração

Entregar uma PWA demonstrável com receitas e despesas, reserva, chat com RAG, quatro agentes e processamento de imagens. Com dados fictícios, despesas essenciais mensais de R$ 2.000,00 e cobertura de três meses geram meta de R$ 6.000,00; saldo declarado de R$ 600,00 corresponde a 10%.

A usuária consulta gastos, entende o cálculo e recebe orientação com fontes e limites. Ao enviar um comprovante sintético, revisa os campos antes de confirmar a despesa. Se faltarem dados ou evidências, o sistema explicita a limitação. O cenário é comportamento esperado, não funcionalidade certificada nem teste com pessoas reais.

O sucesso avaliado é técnico: implementação, rastreabilidade, qualidade e reprodução. Não se promete aumento de renda, adesão, retenção ou melhoria financeira real.

---

## 2. Stakeholders e personas de referência

### Mapa de relações e responsabilidades

- Usuárias de referência: orientam necessidades assumidas; controlam registros e confirmação de despesas. Não houve consulta a usuárias nesta etapa.
- Equipe do Grupo 11: frontend implementa interface; backend controla regras, autorização e persistência; dados/RAG cuida de corpus e recuperação; IA/imagens implementa agentes e extração.
- Revisores e avaliação técnica da equipe: conferem critérios, testes, métricas e evidências; aprovação do PR é distinta de validação de mercado.
- Docentes e avaliadores da Residência: definem e avaliam entregáveis; recebem documentos, demonstrações, resultados e apresentação.
- Mentoria, quando disponível: orienta decisões e impedimentos; não substitui implementação ou revisão.
- Instituições e autores das fontes: fornecem material com proveniência e condições de uso; não há parceria ou endosso presumido.
- Responsáveis pela operação: configuram execução, retenção e monitoramento. Podem ser os mesmos integrantes que desenvolvem.

As relações centrais são equipe → implementação → PWA; fontes → corpus → evidências RAG; PWA → demonstração → avaliadores. As necessidades assumidas das usuárias orientam os fluxos. Os quatro agentes são componentes, não stakeholders humanos.

### Três personas fictícias

Clara — renda previsível, registros iniciais. Quer organizar receitas e despesas e entender sua meta. Ainda não informou despesas essenciais ou cobertura desejada. Precisa de categorias, dados faltantes explícitos e cálculo verificável; a IA não escolhe valores como se já tivessem sido declarados.

Luiza — recebimentos variáveis e histórico incompleto. Quer consultar períodos, acompanhar aportes e entender quais dados sustentam o planejamento. Precisa distinguir período incompleto de mês representativo e registros pessoais de exemplos educativos. O sistema não promete renda futura.

Marina — entrada por imagem com revisão. Quer preparar despesas a partir de comprovantes sem perder controle da gravação. Precisa de prévia editável, indicação de campos ambíguos e confirmação ou cancelamento. Repetir uma confirmação não pode duplicar a despesa.

### Necessidades comuns e limites

Consultar transações por período/categoria; acompanhar meta, saldo e progresso; identificar origem e limites das respostas; revisar imagens; manter isolamento entre usuárias. Os perfis variam cenários de demonstração, não segmentos estatísticos. Nomes são inventados; não representam participantes de pesquisa.

Nenhuma persona autoriza ampliar o MVP para movimentação bancária, recomendação individual de ativos ou estimativas pessoais sem dados suficientes.

---

## 3. Escopo, requisitos e arquitetura de referência

### Priorização e requisitos funcionais P0

- RF01–04: autenticação, perfil/contas manuais, CRUD de receitas/despesas/categorias e consultas por período; testes verificam dados próprios e totais conhecidos.
- RF05–07: reserva e dashboard. Meta = despesas essenciais mensais × cobertura. Saldo = inicial + aportes confirmados − retiradas confirmadas. Progresso = 100 × saldo ÷ meta, somente se meta > 0. Cálculos decimais pertencem ao backend.
- RF08–10: corpus com pelo menos 20 fontes únicas, índice reconstruível, busca com ID/fonte/página ou seção/trecho e resposta com relação entre afirmações, evidências e limites.
- RF11–15: Research recupera dados autorizados e RAG; Analysis sintetiza e solicita cálculos; Validation confere suporte e inconsistências; Communication explica conteúdo aprovado. Orquestrador coordena os quatro, com rastros, chat e tratamento de reprovação.
- RF16–17: texto e imagem; extração de valor, data e estabelecimento quando legíveis, prévia editável e confirmação idempotente. Nenhuma despesa antes da confirmação.
- RF18–20: memória limitada e isolada, PWA instalável com offline explícito, instruções reproduzíveis, demonstração, relatório, métricas e limitações.

### Requisitos não funcionais P0

RNF01–04: isolamento por sessão/objeto, ferramentas permitidas sem SQL livre, minimização de contexto, separação do corpus e proteção de credenciais/HTTPS. Duas usuárias e entradas adversariais verificam ausência de acesso indevido.

RNF05–08: upload/retenção controlados, logs sanitizados, falhas seguras e reprodução com proveniência. Testes induzem falhas e repetem confirmações; não deve ocorrer gravação indevida ou duplicada.

RNF09–11: interface responsiva, rótulos/foco/teclado e erros em texto, avaliação com denominadores e limites operacionais configurados. Verificar navegadores, resoluções e limites definidos pela equipe, sem alegar certificação ou SLA não medido.

### Componentes e exclusões

React + TypeScript/PWA → Django/Django Ninja → PostgreSQL para dados pessoais; pacote de IA consulta ferramentas autorizadas e RAG/Chroma educativo. Modelos não recebem credenciais de banco. OCR propõe campos, backend persiste após confirmação. Agentes podem usar fixtures identificadas no protótipo S4; a integração S6 exige APIs reais.

P1: alertas, relatórios avançados e personalizações não bloqueantes. Fora do MVP: Open Finance, sincronização bancária, pagamentos/transferências reais, recomendação individual de ativos e validação de mercado. Saldos são autodeclarados, não patrimônio bancário verificado.

---

## 4. Riscos, premissas, métricas e evidências

### Riscos prioritários e mitigação

- R01/R06 — acesso cruzado ou instrução maliciosa: autorização determinística por sessão/objeto e ferramentas tipadas; testar duas usuárias e entradas adversariais.
- R02/R03 — alucinação, citação sem suporte ou cálculo errado: RAG com proveniência, validação/abstenção e cálculo decimal no backend; revisar afirmações e casos com resultado conhecido.
- R04/R05 — gravação sem confirmação ou duplicação: prévia editável e confirmação idempotente; conferir banco antes/depois, cancelamento, repetição e concorrência.
- R07/R08 — vazamento ou indisponibilidade: contexto mínimo, memória isolada, logs sanitizados, retenção e timeout; testar expiração e falhas de serviços.
- R09–11 — perda de pesquisa, avaliação enviesada e escopo excessivo: inventário e migração revisada, dataset único com falhas reportadas e prioridade P0.

Impactos são altos ou críticos, estimados qualitativamente; probabilidades ainda não foram medidas. Riscos permanecem abertos até seus controles serem implementados e testados. As frentes correspondentes propõem controles; responsáveis nominais são definidos nas issues.

### Premissas e decisões pendentes

Público/personas são premissas; dados são declarados; corpus é educativo; modelos e recursos ainda serão selecionados; experimentos antigos são referência. Definir período-base e arredondamento da reserva, sessão, limites de upload/memória, retenção, timeout, cache offline e metas de qualidade antes do aceite correspondente.

### Métricas e protocolo propostos

Cobertura: contar fontes únicas verificáveis (mínimo 20) e perguntas com fonte disponível / perguntas que exigem fonte. Hit@k: perguntas com trecho relevante no top-k / perguntas de recuperação avaliadas, com k fixado.

Correção: respostas integralmente corretas / execuções respondíveis previstas, incluindo falhas e recusas indevidas no denominador. Alucinação: respostas com afirmação sem suporte / respostas geradas avaliadas. Fidelidade: pares afirmação–citação com suporte / pares avaliados; cobertura de suporte conta também afirmações sem citação. Abstenção: recusas adequadas / execuções sem suporte previstas; erro técnico não conta como recusa correta.

Segurança e integridade: casos sem acesso cruzado, cálculos corretos, confirmação/idempotência e falhas seguras / respectivos casos executados. Meta proposta: 100% dos casos críticos executados, zero violações; reportar casos planejados não executados. OCR: acertos por campo / imagens com gabarito legível daquele campo; informar ausentes e ilegíveis. Medir latência por cenário e requisitos com evidência / P0 aplicáveis.

Usar as mesmas perguntas em LLM puro, RAG e RAG com explicação estruturada. Registrar versões, corpus, configuração, contagens, erros e revisores. Denominador zero é não aplicável. Uma pessoa avalia e outra revisa dúvidas; sem segunda revisão, indicar resultado preliminar. Limiares de qualidade ainda pendentes devem ser definidos antes da avaliação final. Nenhum resultado é declarado neste pacote.

### Marcos, rastreabilidade e revisão

S1: pacote de definição; S2: corpus/recuperação; S3: comparação e explicação; S4: quatro agentes; S5: multimodal; S6: integração; S7: entrega final. S8 sem novo entregável definido.

Fontes: PRD v1.1 (16/11/2026), cronograma fornecido e documentos #58–61. Síntese para #62, não substitui os catálogos detalhados. A versão da #61 usada foi o commit 8e52704, ainda em revisão; conferir ajustes antes de aprovar este pacote. Requisitos descritos não equivalem a funcionalidades concluídas.
