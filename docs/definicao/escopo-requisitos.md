# Escopo e requisitos do MVP

Referência: [S1-03 / issue #60](https://github.com/anamattos2/grupo11challenge2/issues/60).
Dependência: [cenário e problema / #58](https://github.com/anamattos2/grupo11challenge2/issues/58).
Data: 16/11/2026. Estado: proposta para revisão da equipe.

Este documento especifica o comportamento a construir, conforme o PRD v1.1 e o
cronograma fornecidos pela equipe. Nenhum requisito abaixo é marcado como
implementado apenas por estar descrito ou aparecer em um experimento existente.
A revisão precisa conferir alinhamento com a versão aprovada da #58.

## 1. Objetivo e priorização

Entregar uma PWA de gestão financeira para mulheres em início de carreira,
com registros autodeclarados, planejamento de reserva de emergência e explicações
por IA fundamentadas em evidências. Dados financeiros pessoais pertencem ao
PostgreSQL; o corpus educativo e seus vetores pertencem ao RAG/Chroma.

| Prioridade | Significado | Tratamento |
|---|---|---|
| P0 | Requisito explícito do desafio, proteção de dados ou mínimo para o fluxo completo | Obrigatório no MVP; distribuir implementação entre as semanas |
| P1 | Melhoria útil, sem bloquear os cenários exigidos | Backlog posterior, somente após estabilizar P0 |
| Fora do MVP | Expansão excluída pelo recorte do projeto | Não implementar como parte da entrega atual |

Todos os RF e RNF listados abaixo são P0. A semana indica o marco de evidência
do cronograma, não uma promessa de conclusão ou ordem rígida de desenvolvimento.
Os componentes de produto devem começar a tempo de permitir a integração S6.

## 2. Requisitos funcionais

| ID | Requisito | Critério de aceite verificável | Marco / vínculo |
|---|---|---|---|
| RF01 | Autenticar e encerrar sessão | Usuária com credenciais válidas acessa rotas protegidas; requisição sem autenticação ou após encerrar sessão não acessa seus dados | S6 / DEV01 |
| RF02 | Manter perfil e contas manuais | Usuária cria e edita perfil e conta própria; conta de outra usuária não pode ser consultada ou alterada pelo identificador | S6 / DEV01–02 |
| RF03 | Registrar receitas e despesas categorizadas | Criar, consultar, editar e excluir transações próprias; valores, tipo, data e categoria são validados; entrada inválida não é persistida | S6 / DEV02 |
| RF04 | Consultar registros por período e categoria | Para um conjunto fictício conhecido, a API retorna apenas os registros autorizados e os totais correspondentes ao filtro, com período e moeda identificados | S6 / DEV02, DEV07 |
| RF05 | Definir meta da reserva | Backend multiplica despesas essenciais mensais por meses de cobertura informados; exemplo de R$ 2.000,00 e 3 meses resulta em R$ 6.000,00; informação insuficiente gera estado explícito | S6 / DEV03 |
| RF06 | Registrar saldo inicial, aportes e retiradas declarados | Backend retorna saldo inicial mais aportes confirmados menos retiradas confirmadas; R$ 500,00 + R$ 200,00 − R$ 100,00 resulta em R$ 600,00 | S6 / DEV03 |
| RF07 | Exibir dashboard e progresso da reserva | Interface exibe resultados da API; saldo R$ 600,00 e meta R$ 6.000,00 geram 10%; meta zero gera estado sem progresso calculável, sem divisão por zero | S6 / DEV03 |
| RF08 | Ingerir corpus educativo curado | Pelo menos 20 documentos-fonte únicos têm identificação e origem verificáveis; extração, chunking e embeddings permitem reconstruir o índice Chroma | S2 / S2-01–03, DEV04 |
| RF09 | Recuperar evidências documentais | Consulta retorna ID, fonte, página ou seção e trecho; demonstração permite localizar o texto no documento; busca sem suporte retorna ausência de evidências | S2 / DEV04 |
| RF10 | Responder com explicação estruturada | Resposta identifica afirmações, evidências que as sustentam e limites; referência inexistente ou alegação sem suporte é detectada; informação ausente não vira afirmação factual | S3 / S3-02, DEV05 |
| RF11 | Implementar Research Agent | Rastro identifica consulta ao RAG e, no fluxo integrado, consulta financeira autorizada; saída separa evidência documental de resultado pessoal | S4; integração S6 / S4-01, DEV06–07 |
| RF12 | Implementar Analysis Agent | Rastro associa análise às evidências e aos resultados determinísticos do backend; dados ausentes são explicitados; LLM não fornece aritmética oficial da reserva | S4; integração S6 / S4-02, DEV06 |
| RF13 | Implementar Validation Agent | Cenários com inconsistência, citação inválida e falta de suporte produzem reprovação ou abstenção estruturada; falha de autorização também é impedida nas ferramentas | S4 / S4-03, DEV06 |
| RF14 | Implementar Communication Agent e orquestração | Demonstração mostra os quatro papéis e suas trocas; comunicação usa conteúdo aprovado, referências e limites; saída reprovada não é apresentada como validada | S4 / S4-04, DEV06 |
| RF15 | Oferecer chat para perguntas pessoais e educativas | Pela interface, consulta pessoal usa resultados autorizados da API e consulta educativa usa RAG; usuário distingue origens; indisponibilidade gera mensagem compreensível | S6 / DEV07, DEV10 |
| RF16 | Extrair dados de imagem de comprovante | Imagem sintética produz valor, data e estabelecimento quando legíveis; campos ausentes ou ambíguos são sinalizados e extração parcial não inventa valores | S5 / S5-01, DEV08 |
| RF17 | Revisar e confirmar a despesa extraída | Prévia pode ser editada ou cancelada; antes da confirmação não há despesa; confirmar uma prévia própria persiste uma vez e repetir a confirmação não duplica o registro | S5 / DEV08 |
| RF18 | Manter memória conversacional limitada | Contexto da mesma sessão autorizada pode ser recuperado até o limite configurado; sessões de outra usuária não compartilham histórico; expiração segue a política definida | S6 / S6-02, DEV09 |
| RF19 | Disponibilizar PWA instalável e comportamento offline explícito | Em navegador compatível de referência, instalação é demonstrada; desconexão exibe estado previsto; operação financeira offline não aparece como salva sem confirmação do backend | S6 / DEV10 |
| RF20 | Entregar demonstração e documentação final | Ambiente limpo executa instruções publicadas com dados fictícios; relatório, apresentação, métricas, limitações e evidências dos requisitos estão vinculados ao repositório | S7 / S7-01–02, DEV11 |

Os agentes podem usar ferramentas com dados fictícios explicitamente
identificados no protótipo S4. Na aplicação integrada S6, consultas pessoais e
cálculos precisam usar as APIs reais do backend autenticado. O orquestrador não
conta como um dos quatro agentes.

### Regras financeiras transversais

- A meta é despesas essenciais mensais × meses de cobertura.
- O saldo declarado é saldo inicial + aportes confirmados − retiradas confirmadas.
- O progresso é 100 × saldo declarado ÷ meta, somente quando meta > 0.
- Backend é a fonte dos cálculos; valores monetários usam representação decimal.
- Datas, período consultado e moeda acompanham resultados financeiros.
- O saldo é autodeclarado: não representa saldo bancário verificado.
- Uma pergunta ou extração de imagem não autoriza gravação financeira por si só.

## 3. Requisitos não funcionais

| ID | Requisito | Critério de aceite verificável | Vínculo |
|---|---|---|---|
| RNF01 | Isolamento e autorização determinística | Teste com duas usuárias tenta listar, consultar e alterar objetos da outra por ID, sessão e ferramenta; nenhuma operação revela ou modifica dados alheios | DEV01, DEV07, DEV09 |
| RNF02 | Controle das ferramentas de IA | Backend valida operação e parâmetros permitidos; identidade vem da sessão; prompt pedindo SQL livre ou acesso cruzado não concede acesso; conteúdo de documentos não executa instruções | DEV06–07 |
| RNF03 | Minimização e separação dos dados | Teste de ingestão não indexa registros pessoais ou comprovantes no corpus educativo; contexto enviado ao modelo é limitado ao necessário e à política aprovada | DEV04, DEV08–09 |
| RNF04 | Configuração e credenciais protegidas | Exemplos usam valores fictícios; repositório e evidências não contêm credenciais reais; serviços expostos usam HTTPS na implantação | DEV01, DEV10 |
| RNF05 | Upload e retenção controlados | Arquivo inválido ou acima do limite configurado é rejeitado sem gravação financeira; acesso a imagem exige autorização; expiração e exclusão são verificadas com a política adotada | DEV08, DEV10 |
| RNF06 | Observabilidade sem conteúdo sensível | Logs de uma consulta registram correlação, etapa, tempo e status; inspeção de falhas induzidas não encontra senhas, imagens completas ou extratos em bruto | DEV10 |
| RNF07 | Falhas seguras e integridade | Interromper LLM, vetor, OCR ou ferramenta resulta em erro ou estado parcial explícito, sem registro indevido; repetição de confirmação e tentativa concorrente não duplicam a despesa | DEV03, DEV08, DEV10 |
| RNF08 | Reprodutibilidade e preservação | Instruções permitem reconstruir ambiente e índice; versão de código, corpus, modelos e parâmetros acompanham avaliações; migrações preservam origem e resultados únicos | DEV04–05, DEV10–11 |
| RNF09 | Experiência responsiva e acessível nos fluxos críticos | Em resolução móvel e desktop de referência, login, transações e chat têm rótulos, foco visível, navegação por teclado e erros em texto; informação crítica não depende só de cor | DEV10 |
| RNF10 | Qualidade avaliada sem métricas inventadas | Dataset inclui casos com e sem suporte; relatório compara LLM puro, RAG e RAG com explicação, indicando método, avaliadores, denominadores e limitações | S3-01–03, DEV05 |
| RNF11 | Limites operacionais observáveis | Timeout, volume de memória e tamanho de arquivo são configurados e documentados; testes nos limites geram resposta prevista; latência é medida, sem declarar SLA não validado | DEV08–10 |

RNF09 é um critério mínimo de verificação dos fluxos, não uma certificação de
conformidade de acessibilidade. RNF10 não fixa uma taxa de acerto arbitrária:
limiares de qualidade devem ser definidos antes de selecionar a configuração
final e os resultados efetivamente medidos devem ser reportados.

## 4. Melhorias posteriores e exclusões

P1, sem compromisso para a entrega: alertas opcionais, relatórios financeiros
mais detalhados e personalizações visuais além do necessário para os fluxos.
Essas melhorias não podem substituir evidências obrigatórias das semanas.

Fora do MVP:

- Open Finance, importação automática e sincronização de contas bancárias.
- Pagamentos, transferências ou movimentação bancária real.
- Recomendação individual de ativos ou execução de investimentos.
- Integrações externas sem necessidade demonstrada para o desafio.
- Validação de mercado, aquisição, adesão ou retenção com usuárias reais.
- Alegações de que a aplicação melhora renda, poupança ou saúde financeira sem
  pesquisa e medição próprias.

## 5. Cenários integradores de aceite

| Cenário com dados fictícios | Resultado esperado | Requisitos principais |
|---|---|---|
| Perguntar quanto foi gasto em uma categoria no período informado | Total calculado pela API com origem e período; nenhum dado de outra usuária | RF04, RF11–15; RNF01–02 |
| Perguntar como iniciar a reserva | Meta calculada no backend ou pedido de dados faltantes, orientação educativa com suporte e limites | RF05–07, RF09–14; RNF10 |
| Enviar imagem, corrigir campos e confirmar duas vezes | Nenhuma despesa antes da confirmação e uma única despesa depois | RF16–17; RNF05, RNF07 |
| Perguntar algo sem evidência ou com fonte inconsistente | Validation identifica o problema e a comunicação não afirma conteúdo reprovado | RF09–10, RF13–14; RNF02 |
| Induzir falha de serviço ou trocar a sessão | Mensagem segura, log sanitizado, histórico isolado e ausência de alteração indevida | RF15, RF18; RNF01, RNF06–07 |

## 6. Decisões necessárias antes da implementação correspondente

| Tema | Definição pendente | Frente responsável pela proposta |
|---|---|---|
| Reserva | Período-base das despesas essenciais, arredondamento, validação de meses e política de retirada acima do saldo | Backend + qualidade |
| Sessão | Mecanismo de autenticação, expiração, CSRF/CORS e recuperação de acesso | Backend + frontend |
| Imagem | Formatos, tamanho máximo, retenção e critérios de duplicação provável | Imagens + backend |
| Memória e modelos | Quantidade/idade de mensagens, timeout, provedor e dados autorizados no contexto | IA + backend |
| PWA | Navegadores e resoluções de referência, cache, limpeza no logout e bloqueio ou sincronização offline | Frontend + backend |
| Avaliação | Dataset, critérios de revisão, metas de qualidade e tratamento de desacordo entre avaliadores | RAG + qualidade |

As decisões precisam ser registradas e convertidas em valores de teste antes
de aceitar o componente correspondente. Uma pendência não permite marcar o
requisito como atendido. A #61 detalhará riscos, premissas e métricas sem duplicar
este catálogo; a #62 consolidará o pacote de definição de 3 a 5 páginas.

## 7. Rastreabilidade e revisão desta issue

| Critério da #60 | Evidência neste documento |
|---|---|
| Requisitos com critérios verificáveis | Seções 2–3: RF01–20 e RNF01–11; cenários integradores na seção 5 |
| Autenticação, finanças, RAG, agentes, imagem e PWA contemplados | RF01–19, com marcos e vínculos ao PRD |
| Open Finance, movimentação bancária e recomendação de ativos fora do MVP | Seção 4: exclusões explícitas |

Nesta issue, a revisão aprova a especificação; não certifica execução dos
cenários. Cada implementação deve ligar seus testes e evidências aos IDs acima.
Os códigos Sx-yy e DEVxx citados nas tabelas são requisitos do PRD, não números
de issues GitHub. Confira a [#58](https://github.com/anamattos2/grupo11challenge2/issues/58)
e as [personas da #59](https://github.com/anamattos2/grupo11challenge2/issues/59)
na revisão para manter coerência do recorte.

## 8. Referências

- [Issue #60](https://github.com/anamattos2/grupo11challenge2/issues/60).
- [Arquitetura inicial](../arquitetura/arquitetura-inicial.md).
- PRD v1.1 e Matriz de Rastreabilidade do Desafio 02, Grupo 11, de 16/11/2026,
  fornecido pela equipe em `PRD_v1_1_Desafio_02_Grupo11.html`.
- Cronograma de referência fornecido em
  `Cronograma Semanal_Superficial_Tudo_pode_mudar.docx`, semanas 1 a 7.

Os dois arquivos de referência foram fornecidos na conversa e ainda não estão
versionados nesta base. As tabelas sintetizam o escopo sem afirmar aprovação
dos critérios pela equipe antes da revisão do PR.
