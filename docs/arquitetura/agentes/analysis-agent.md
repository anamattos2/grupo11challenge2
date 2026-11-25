# Analysis Agent

Referência: [S4-03 / #77](https://github.com/anamattos2/grupo11challenge2/issues/77).
Depende dos contratos da S4-01 (#75) e usa a Research da S4-02 (#76) nos testes.
Código: `packages/ai/src/finance_ai/agents/analysis.py` e `redacao.py`.

## 1. Papel

A Analysis recebe a pergunta e a `SaidaPesquisa` e devolve uma `SaidaAnalise`
com até cinco afirmações curtas. Cada afirmação cita as evidências que a
sustentam. Ela **não busca dados** (quem busca é a Research), **não calcula
valores** (quem calcula é o backend, decisão D05) e **não escreve a resposta
final** (isso é da Communication).

| Pode | Não pode |
|---|---|
| Escolher quais evidências respondem à pergunta | Citar evidência que não recebeu |
| Pedir um número que falta ao backend (`PedidoCalculo`) | Fazer conta, mesmo simples |
| Comparar dois valores do backend ("maiores", "menores") por código | Escrever um número que não veio de ferramenta |
| Dizer o que falta (`Lacuna`) | Responder só a parte conceitual quando a parte pessoal ficou sem dados |

## 2. Como funciona

Subgrafo LangGraph com quatro nós:

```
START → diagnosticar ─┬─ pedir_calculo ─────────────┐
                      ├─ dados_insuficientes ───────┤
                      └─ redigir → conferir ────────┴→ END
```

**diagnosticar** (só código). Lê a pergunta com as mesmas palavras-chave do
planejador da Research e decide o que ela precisa: transações de quais meses
(`periodos_da_pergunta` reconhece "outubro ou setembro", "este mês", "mês
passado"), saldo das contas, situação da reserva, orientação educativa. Depois
procura cada necessidade nas evidências. Negada ou erro são casados com a
**mesma consulta** (operação, período e filtro de essenciais, que a Research
agora grava em `RegistroChamada.parametros`): um erro em setembro não impede
pedir outubro.

| Situação | Resultado |
|---|---|
| Dado presente | Vai para a redação |
| Dado ausente e nunca consultado | `PedidoCalculo` para o backend (uma rodada) |
| Dado ausente porque a consulta foi negada | Lacuna: "Esta conversa não tem permissão para consultar…" |
| Dado ausente porque a consulta deu erro, ou ainda falta depois da rodada | Lacuna: "Não consegui consultar … agora." |
| Mais de 3 meses na pergunta | Analisa os 3 primeiros e registra `periodo_excedido` com os meses que ficaram de fora |
| Comparação com valor nulo vindo do backend | Não compara; lacuna "Não dá para comparar os períodos…" |
| Backend respondeu, mas não conseguiu calcular (reserva sem cadastro) | Lacuna com o que falta cadastrar, traduzido para a leitora |
| Pergunta sem período | Responde o mês corrente e registra lacuna `periodo_nao_informado` |
| Despesas essenciais sem registros | Diz "Não há despesas essenciais registradas…" e registra `sem_categoria_essencial` |
| Parte conceitual sem trecho relevante | Lacuna `sem_fonte_documental` |

Trechos de documento que tentam dar instrução ao assistente ("ignore as
instruções…") são descartados inteiros, antes de qualquer redação.

**Roteamento.** Se há pedidos de cálculo, sai `precisa_calculo`. Se a pergunta
é sobre os dados da usuária e nenhum dado pessoal está disponível, sai
`dados_insuficientes`, mesmo que haja trechos educativos: responder só a parte
conceitual de "como está minha reserva?" esconderia a lacuna. O orquestrador
transforma isso em pedido de complemento, com as perguntas das lacunas.

**redigir.** Um `Redator` escreve rascunhos. Há dois:

- `RedatorPorRegras`: frases-modelo, determinístico (padrão);
- `RedatorLLM`: chat model com `with_structured_output`, por exemplo Ollama
  local (`modelo_ollama()`); se o modelo cair, demorar ou devolver lixo, as
  regras assumem.

**conferir.** `materializar` transforma cada rascunho em `Afirmacao` ou o
recusa. O id vem da posição do rascunho (`a1` é sempre o primeiro), então uma
recusa não renumera os outros. Depois aplica o feedback de uma revisão e monta
a saída. Se a pergunta pede dado pessoal e nenhuma afirmação pessoal passou,
a saída é `dados_insuficientes`, nunca `analisada` só com a parte conceitual;
sem lacuna do diagnóstico, entra a lacuna `dados_pessoais_sem_suporte`. Com
o `RedatorLLM`, esse caso (ou nenhum rascunho aproveitável) aciona as regras
antes.

## 3. Números só por referência

O redator, seja regra ou LLM, **nunca digita um valor da usuária**. Ele escreve
marcadores que apontam para valores que o backend já calculou:

```text
rascunho:  Em {{fin:resumo_transacoes:cad0c2b2ac81|periodo}} você registrou
           {{fin:resumo_transacoes:cad0c2b2ac81|despesas}} em despesas essenciais.
afirmação: Em outubro de 2026 você registrou R$ 1.850,40 em despesas essenciais.
```

`materializar` recusa o rascunho quando:

| Problema | Exemplo |
|---|---|
| Algarismo fora de marcador numa afirmação sobre dados pessoais | "Você gastou R$ 2.000,00", "o dobro de 965,20" |
| Marcador para evidência ou chave inexistente | `{{fin:resumo_transacoes:000000000000|despesas}}`, `|lucro` |
| Marcador para valor que o backend devolveu nulo | `falta` de uma reserva sem cadastro |
| Orientação educativa citando dado financeiro | "Guarde {{…|despesas}} por mês" |
| Orientação educativa com número que não está no trecho | "Guarde 15% da renda" |
| Afirmação pessoal sem evidência financeira | "Você gasta demais" citando só um documento |

Por último, ainda aplica a regra `numeros_conferem` (todo número do texto está
nas evidências citadas) como defesa em profundidade. A natureza é decidida
pelo código: usar um valor derivado pelo backend (`resultado`, `falta`,
`progresso_percentual`, `saldo_total_declarado`, `meta`) torna a afirmação
`calculo`.

**Comparação.** "Gastei mais em outubro ou em setembro?" precisa dos dois
meses. Se a Research trouxe só um, a Analysis pede o outro ao backend. Com os
dois, o código compara os valores (`redacao.comparar`, `Decimal`) e a frase
diz "maiores", "menores" ou "iguais", sem número novo. A diferença em reais
exigiria uma operação nova do backend (pendência abaixo).

## 4. LLM: o que ele vê e o que decide

O `RedatorLLM` recebe só o que o diagnóstico separou: os marcadores com os
valores já formatados, as comparações já feitas e as frases relevantes dos
trechos, sem o trecho com instrução embutida e sem a identidade da usuária.
Os trechos vêm marcados como dados, não instruções.

O status (`analisada`, `precisa_calculo`, `dados_insuficientes`, `falha`) é
sempre decidido pelo código. Se a parte pessoal ficou sem dados, o modelo nem
é chamado. O modelo só escolhe as palavras, e qualquer número que ele digitar
é recusado.

Limite conhecido: uma palavra comparativa escrita pelo LLM ("o dobro", "bem
mais") não tem algarismo e não é detectável por regra. Por isso as
comparações vêm prontas do código, e a Validation (S4-04) deve conferir o
sentido das afirmações `calculo`.

## 5. Revisão

Na segunda passada, depois de uma reprovação, a `EntradaAnalise` traz
`feedback_validacao`. O orquestrador acrescenta ao feedback o texto de cada
afirmação reprovada (`fluxo.feedback_para_revisao`), e a Analysis remove as
afirmações **pelo texto**, que é estável entre rodadas mesmo quando a
numeração muda (por exemplo, com o LLM). Só quando não há texto no feedback é
que o id citado é usado. Se não sobrar nenhuma afirmação, devolve `falha` com
`revisao_sem_afirmacoes`; se sobrar só a parte conceitual de uma pergunta
pessoal, devolve `dados_insuficientes`. O `RedatorLLM` também recebe o feedback no
prompt.

## 6. Lacunas chegam à usuária

Lacunas de uma análise parcial (por exemplo, período assumido) agora entram em
`RespostaFinal.limites`, pelo `montar_resposta` do fluxo. Assim a indicação de
dado insuficiente é explícita mesmo quando há resposta. Em
`dados_insuficientes`, as perguntas das lacunas viram `perguntas_complemento`.

## 7. Como rodar

```bash
python -m finance_ai.agents.analysis "Gastei mais em outubro ou em setembro?"
python -m finance_ai.agents.analysis "Como está minha reserva de emergência?" --usuaria usuaria-ficticia-b
python scripts/avaliar_analysis.py                      # redator por regras
python scripts/avaliar_analysis.py --redator ollama     # LLM local, extra llm
```

## 8. Testes

| Arquivo | O que cobre |
|---|---|
| `tests/test_analysis_agent.py` | Os três critérios da issue, materialização, revisão, `RedatorLLM` com modelo falso, integração com o grafo |
| `tests/test_analysis_exaustivo.py` | 14 perguntas × 2 usuárias × 3 permissões × fonte e índice fora do ar × 8 redatores (regras e 7 comportamentos de LLM): mais de 1.800 execuções com rodada de cálculo e revisão, conferindo as invariantes |
| `tests/test_avaliacao_analysis.py` | A baseline da avaliação e um redator que inventa números |

Para ver que os testes exaustivos pegam erro de verdade, a correção foi
quebrada de propósito, uma camada por vez: aceitar trecho com instrução,
deixar orientação citar dado pessoal, remover as duas camadas que barram
número digitado, remover as duas que impedem responder só a parte conceitual.
Em todos os casos o teste falhou.

## 9. Pendências

| Pendência | Onde |
|---|---|
| Diferença e variação entre períodos em reais e percentual | Nova operação do backend (`OperacaoFinanceira`) |
| Conferir o sentido de afirmações `calculo` (comparações) | S4-04 / Validation |
| Mostrar `lacunas` na redação | S4-05 / Communication |
| Comparar redator LLM × regras com o Ollama | Rodar `avaliar_analysis.py --redator ollama` localmente |
| Categorias por nome nas respostas (totais por categoria) | Quando a evidência trouxer valores por categoria |
